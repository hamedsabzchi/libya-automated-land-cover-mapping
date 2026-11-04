"""Display and bounded delivery over the retained graph. No classification changes."""
import math
import re
from html import escape
from .bundle import GraphArtifactStore
from .exports import export_spec, window_bounds
from .jobs import checked_mapping_bundle

PALETTE = ['#002200','#185e0a','#74a56a','#fffb00','#FF8C00','#43BE0A',
           '#bb6d3a','#553a17','#808080','#00008B','#15c0df','#8B4513']
CLASS_NAMES = ['Forest','Shrubland','Grassland','Cultivated rainfed','Cultivated irrigated',
               'Orchards','Bare soil/sand','Rocks','Built up','Artificial water','Seasonal water','Sebkha']
CRS = 'EPSG:32633'
SIDE = 1024


def error_detail(exc):
    """Useful server text, without temporary URLs or authorization values."""
    value=str(exc)
    value=re.sub(r'https?://[^\s<>]+', '[URL omitted]', value)
    value=re.sub(r'(?i)(bearer\s+|(?:access_token|refresh_token|api_key|authorization)\s*[:=]\s*)[^\s,;]+', r'\1[redacted]', value)
    return value[:4000] or type(exc).__name__


class MapDisplayError(RuntimeError):
    def __init__(self,stage,cause):
        self.stage=stage
        self.error_type=type(cause).__name__
        self.detail=error_detail(cause)
        super().__init__(f'{stage}: {self.error_type}: {self.detail}')


def display_step(stage,action):
    try:return action()
    except Exception as exc:raise MapDisplayError(stage,exc) from exc


def legend_html():
    return '<b>Land-cover classes</b><div style="display:flex;flex-wrap:wrap;gap:6px">'+''.join(
        f'<span style="min-width:190px"><span style="display:inline-block;width:14px;height:14px;background:{color};border:1px solid #888"></span> {i} · {escape(name)}</span>'
        for i,(name,color) in enumerate(zip(CLASS_NAMES,PALETTE),1))+'</div>'


def tile_spec(column, row):
    if type(column) is not int or type(row) is not int or column % SIDE or row % SIDE:
        raise ValueError('Select an aligned grid tile on the map.')
    return export_spec({'crs':CRS,'transform':[10,0,0,0,-10,0], 'folder_prefix':'LibyaLandCover_Tile',
        'max_pixels':SIDE*SIDE,'file_dimensions':SIDE,
        'pixel_window':{'column':column,'row':row,'width':SIDE,'height':SIDE}})


def tile_at(lon, lat):
    from pyproj import Transformer
    if not all(type(v) in (int,float) and math.isfinite(v) for v in (lon,lat)) or not -180<=lon<=180 or not -85<=lat<=85:
        raise ValueError('Select a valid point on the map.')
    x,y=Transformer.from_crs('EPSG:4326',CRS,always_xy=True).transform(lon,lat)
    return tile_spec(math.floor(x/(10*SIDE))*SIDE,math.floor(-y/(10*SIDE))*SIDE)


def feature(spec):
    from pyproj import Transformer
    transform=Transformer.from_crs(CRS,'EPSG:4326',always_xy=True)
    x0,y0,x1,y1=window_bounds(spec)
    points=[]
    for a,b in [((x0,y0),(x1,y0)),((x1,y0),(x1,y1)),((x1,y1),(x0,y1)),((x0,y1),(x0,y0))]:
        points += [list(transform.transform(a[0]+(b[0]-a[0])*i/8,a[1]+(b[1]-a[1])*i/8)) for i in range(8)]
    points.append(points[0])
    w=spec['pixel_window']
    return {'type':'Feature','properties':{'column':w['column'],'row':w['row'],
            'label':f"Tile {w['column']//SIDE}, {w['row']//SIDE}"},
            'geometry':{'type':'Polygon','coordinates':[points]}}


def visible_grid(bounds, area_xy, limit=400):
    """Only send the visible grid to the browser. All area cells remain selectable."""
    from pyproj import Transformer
    if not bounds: return {'type':'FeatureCollection','features':[]},False
    (south,west),(north,east)=bounds
    box=Transformer.from_crs('EPSG:4326',CRS,always_xy=True).transform_bounds(west,south,east,north,densify_pts=21)
    x0,y0,x1,y1=max(box[0],area_xy[0]),max(box[1],area_xy[1]),min(box[2],area_xy[2]),min(box[3],area_xy[3])
    empty={'type':'FeatureCollection','features':[]}
    if x0>=x1 or y0>=y1:return empty,False
    c0,c1=math.floor(x0/10240),math.ceil(x1/10240)
    r0,r1=math.floor(-y1/10240),math.ceil(-y0/10240)
    if (c1-c0)*(r1-r0)>limit:return empty,True
    return {'type':'FeatureCollection','features':[feature(tile_spec(c*SIDE,r*SIDE))
            for c in range(c0,c1) for r in range(r0,r1)]},False


class MapBackend:
    def __init__(self, store): self.store=store

    def source(self, mapping_id):
        import ee
        mapping=self.store.get(mapping_id)
        if mapping['kind']!='mapping' or mapping['state']!='completed':
            raise ValueError('Wait for map preparation to finish.')
        checked=checked_mapping_bundle(self.store,mapping)
        request=checked['request'].to_dict()
        ee.Initialize(project=checked['manifest']['project'])
        result=checked['result'].to_dict()
        artifact=next(o['artifact_id'] for o in result['outputs'] if o['kind']=='final_map')
        image=GraphArtifactStore(self.store.folder(mapping_id)/'bundle').get(result['run_id'],artifact)
        aoi=ee.FeatureCollection(request['aoi_asset']).geometry()
        return ee,checked,artifact,image,aoi

    def open(self, mapping_id):
        ee,checked,artifact,image,aoi=display_step('restore_saved_map',lambda:self.source(mapping_id))
        # Clip to the full actual AOI, never to the old pilot window. No resampling.
        tiles=display_step('request_land_cover_layer',lambda:image.clip(aoi).getMapId({'min':1,'max':12,'palette':PALETTE}))
        # Read complete GeoJSON: GeometryCollection has geometries, not coordinates.
        # Simplification affects the outline only; classification clipping is exact.
        outline=display_step('read_study_area_boundary',lambda:aoi.simplify(100).transform('EPSG:4326',10).getInfo())
        geometries=display_step('read_study_area_boundary',lambda:ee.Dictionary({
            'wgs_bounds':aoi.bounds(10,'EPSG:4326').coordinates(),
            'utm_bounds':aoi.bounds(10,ee.Projection(CRS)).coordinates()}).getInfo())
        ring=geometries['wgs_bounds'][0];xy=geometries['utm_bounds'][0]
        west,east=min(p[0] for p in ring),max(p[0] for p in ring)
        south,north=min(p[1] for p in ring),max(p[1] for p in ring)
        return {'mapping_id':mapping_id,'artifact_id':artifact,'request':checked['request'].to_dict(),
            'url':tiles['tile_fetcher'].url_format,'bounds':[[south,west],[north,east]],
            'area_xy':[min(p[0] for p in xy),min(p[1] for p in xy),max(p[0] for p in xy),max(p[1] for p in xy)],
            'outline':{'type':'Feature','properties':{},'geometry':outline}}

    def plan(self,mapping_id,spec):
        ee,checked,artifact,image,aoi=self.source(mapping_id)
        w=spec['pixel_window'];spec=tile_spec(w['column'],w['row'])
        rectangle=ee.Geometry.Rectangle(window_bounds(spec),proj=CRS,geodesic=False)
        overlap=rectangle.intersection(aoi,maxError=1,proj=ee.Projection(CRS)).area(1,ee.Projection(CRS)).getInfo()
        if type(overlap) not in (int,float) or not math.isfinite(overlap) or overlap<=0:
            raise ValueError('This tile is outside the study area. Select another tile inside the outline.')
        return artifact,{'spec':spec,'bounds_xy':window_bounds(spec),'pixel_count':SIDE*SIDE,
            'aoi_overlap_m2':overlap,'selection':'map_grid','valid_raster_pixels_verified':False}
