// ============================================================================
// LIBYA GUIDED AUTOMATED LAND-COVER MAPPING APP
// By: Hamed Sabzchi Dehkharghani
// Independent personal technical portfolio and research-development project.
// ============================================================================

ui.root.clear();

var map = ui.Map();
map.setOptions('HYBRID');
var panel = ui.Panel({style: {width: '430px', padding: '10px'}});
ui.root.add(ui.SplitPanel(panel, map, 'horizontal', false));

var EMBEDDING_COLLECTION = 'GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL';
var DEM_IMAGE = 'USGS/SRTMGL1_003';
var EMBEDDING_FIRST_YEAR = 2017;
var EMBEDDING_LAST_YEAR = 2024;

var CLASS_VALUES = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
var CLASS_NAMES = [
  'Forest', 'Shrubland', 'Grassland', 'Cultivated rainfed',
  'Cultivated irrigated', 'Orchards', 'Bare soil/sand', 'Rocks',
  'Built up', 'Artificial water', 'Seasonal water', 'Sebkha'
];
var PALETTE = [
  '002200', '185e0a', '74a56a', 'fffb00', 'FF8C00', '43BE0A',
  'bb6d3a', '553a17', '808080', '00008B', '15c0df', '8B4513'
];
var DEFAULT_SEEDS = [42, 123, 256, 389, 512, 645, 778, 891, 999, 1111, 2222, 3333, 4444, 5555];

var state = {result: null, config: null, running: false};

function heading(text) {
  return ui.Label(text, {fontWeight: 'bold', fontSize: '16px', margin: '10px 0 4px 0'});
}
function note(text) {
  return ui.Label(text, {fontSize: '11px', color: '#555', whiteSpace: 'pre-wrap'});
}
function textInput(label, value) {
  panel.add(ui.Label(label, {fontWeight: 'bold', margin: '5px 0 1px 0'}));
  var box = ui.Textbox({value: String(value), style: {stretch: 'horizontal'}});
  panel.add(box);
  return box;
}
function numberValue(value, label, min, max) {
  var x = Number(value);
  if (!isFinite(x) || x < min || x > max) throw label + ' must be between ' + min + ' and ' + max + '.';
  return x;
}
function cleanName(value) {
  return String(value).trim().replace(/[^A-Za-z0-9_-]+/g, '_');
}

panel.add(ui.Label('Libya Automated Land-Cover Mapping', {
  fontWeight: 'bold', fontSize: '21px', color: '#1b5e20'
}));
panel.add(note('By: Hamed Sabzchi Dehkharghani'));
panel.add(note(
  'Independent personal project. Dataset names identify sources only and do not imply institutional authorship or endorsement.'
));

panel.add(heading('1. Earth Engine assets'));
var aoiBox = textInput('AOI FeatureCollection asset', 'projects/practical-proxy-441422-n6/assets/Libya/Fezzan');
var trainingBox = textInput('Training points FeatureCollection asset', 'projects/practical-proxy-441422-n6/assets/Libya/TD-V4');
var classFieldBox = textInput('Class field', 'lc_code');
panel.add(note(
  'The default AOI and training assets are external personal Earth Engine dependencies and are not bundled with this repository. Replace them if you do not have access.'
));

panel.add(heading('2. Assessment period'));
var targetYearBox = textInput('Priority year', 2024);
var yearCountBox = textInput('Number of annual maps', 5);
var fallbackYearBox = textInput('Fallback year for masked priority pixels', 2023);
panel.add(note('Satellite Embedding V1 annual layers currently cover 2017–2024 in the public Earth Engine catalog.'));

panel.add(heading('3. Random Forest controls'));
var trainFractionBox = textInput('Training fraction', 0.70);
var treesBox = textInput('Trees per annual model', 500);
var scaleBox = textInput('Processing/export scale (m)', 10);
var targetAccuracyBox = textInput('Minimum producer-accuracy target (%)', 60);
panel.add(note('Class 8 (Rocks) remains mapped and reported but is excluded from the default stopping threshold, matching the reference workflow.'));

panel.add(heading('4. Output'));
var prefixBox = textInput('Export name prefix', 'libya_landcover');
var statusLabel = ui.Label('Ready.', {fontWeight: 'bold', whiteSpace: 'pre-wrap', margin: '10px 0'});
var resultsPanel = ui.Panel();
var runButton = ui.Button({label: 'RUN AUTOMATED MAPPING', style: {stretch: 'horizontal'}});
var exportButton = ui.Button({label: 'EXPORT GEOTIFF TO DRIVE', disabled: true, style: {stretch: 'horizontal'}});
panel.add(runButton);
panel.add(exportButton);
panel.add(statusLabel);
panel.add(heading('5. Validation summary'));
panel.add(resultsPanel);

function setStatus(text, color) {
  statusLabel.setValue(text);
  statusLabel.style().set('color', color || '#333');
}

function readConfig() {
  var targetYear = Math.round(numberValue(targetYearBox.getValue(), 'Priority year', EMBEDDING_FIRST_YEAR, EMBEDDING_LAST_YEAR));
  var yearCount = Math.round(numberValue(yearCountBox.getValue(), 'Number of annual maps', 1, 8));
  var years = [];
  for (var i = 0; i < yearCount; i++) years.push(targetYear - i);
  if (years[years.length - 1] < EMBEDDING_FIRST_YEAR) {
    throw 'The selected year window extends before ' + EMBEDDING_FIRST_YEAR + '.';
  }
  return {
    aoi: aoiBox.getValue().trim(),
    training: trainingBox.getValue().trim(),
    classField: classFieldBox.getValue().trim(),
    targetYear: targetYear,
    years: years,
    fallbackYear: Math.round(numberValue(fallbackYearBox.getValue(), 'Fallback year', EMBEDDING_FIRST_YEAR, EMBEDDING_LAST_YEAR)),
    trainFraction: numberValue(trainFractionBox.getValue(), 'Training fraction', 0.05, 0.95),
    trees: Math.round(numberValue(treesBox.getValue(), 'Trees', 1, 5000)),
    bagFraction: 0.95,
    scale: numberValue(scaleBox.getValue(), 'Scale', 1, 1000),
    tileScale: 16,
    targetAccuracy: numberValue(targetAccuracyBox.getValue(), 'Accuracy target', 0, 100),
    excludedThresholdClass: 8,
    seeds: DEFAULT_SEEDS,
    prefix: cleanName(prefixBox.getValue()) || 'libya_landcover'
  };
}

function getEmbedding(year, geometry) {
  var start = ee.Date.fromYMD(year, 1, 1);
  return ee.ImageCollection(EMBEDDING_COLLECTION)
    .filterDate(start, start.advance(1, 'year'))
    .filterBounds(geometry)
    .mosaic();
}

function terrainImage() {
  var dem = ee.Image(DEM_IMAGE);
  return ee.Image.cat([
    dem.select('elevation'),
    ee.Terrain.slope(dem),
    ee.Terrain.aspect(dem)
  ]).rename(['elevation', 'slope', 'aspect']);
}

function normalizedTraining(cfg) {
  return ee.FeatureCollection(cfg.training).map(function(feature) {
    return feature.set(cfg.classField, ee.Number.parse(ee.String(feature.get(cfg.classField))));
  }).filter(ee.Filter.inList(cfg.classField, CLASS_VALUES));
}

function stratifiedSplit(points, cfg, seed) {
  var train = ee.FeatureCollection([]);
  var validation = ee.FeatureCollection([]);
  CLASS_VALUES.forEach(function(classValue) {
    var subset = points
      .filter(ee.Filter.eq(cfg.classField, classValue))
      .randomColumn('random', seed);
    train = train.merge(subset.filter(ee.Filter.lt('random', cfg.trainFraction)));
    validation = validation.merge(subset.filter(ee.Filter.gte('random', cfg.trainFraction)));
  });
  return {train: train, validation: validation};
}

function temporalDecision(yearly, cfg) {
  var stack = ee.Image.cat(cfg.years.map(function(year) {
    return yearly[year].rename('y' + year);
  }));
  var priority = stack.select('y' + cfg.targetYear);
  var result = stack.reduce(ee.Reducer.mode());
  var class4Count = ee.Image.constant(0);
  var class5Count = ee.Image.constant(0);
  cfg.years.forEach(function(year) {
    var band = stack.select('y' + year);
    class4Count = class4Count.add(band.eq(4));
    class5Count = class5Count.add(band.eq(5));
  });
  return result
    .where(priority.eq(4).or(priority.eq(5)), priority)
    .where(class5Count.gte(2), 5)
    .where(class4Count.gte(2), 4)
    .where(class4Count.gte(2).and(class5Count.gte(2)), priority)
    .rename('classification');
}

function buildCandidate(cfg, seed, roi, points, embeddings, terrain) {
  var split = stratifiedSplit(points, cfg, seed);
  var yearly = {};
  var classifiers = {};

  cfg.years.forEach(function(year) {
    var predictors = ee.Image.cat([embeddings[year], terrain]);
    var samples = predictors.sampleRegions({
      collection: split.train,
      properties: [cfg.classField],
      scale: cfg.scale,
      tileScale: cfg.tileScale,
      geometries: false
    }).filter(ee.Filter.notNull(predictors.bandNames()));

    var classifier = ee.Classifier.smileRandomForest({
      numberOfTrees: cfg.trees,
      bagFraction: cfg.bagFraction,
      seed: seed
    }).train({
      features: samples,
      classProperty: cfg.classField,
      inputProperties: predictors.bandNames()
    });

    classifiers[year] = classifier;
    yearly[year] = predictors.classify(classifier).rename('c' + year);
  });

  var validationMap = temporalDecision(yearly, cfg);
  var validation = validationMap.sampleRegions({
    collection: split.validation,
    properties: [cfg.classField],
    scale: cfg.scale,
    tileScale: cfg.tileScale,
    geometries: false
  });
  var matrix = validation.errorMatrix(cfg.classField, 'classification', CLASS_VALUES);

  return {
    seed: seed,
    map: validationMap.clip(roi),
    yearly: yearly,
    classifiers: classifiers,
    validationPoints: split.validation,
    matrix: matrix
  };
}

function minIncludedProducer(producer, excludedClass) {
  var minimum = 100;
  for (var i = 0; i < CLASS_VALUES.length; i++) {
    if (CLASS_VALUES[i] === excludedClass) continue;
    var x = Number(producer[i]) * 100;
    if (isFinite(x)) minimum = Math.min(minimum, x);
  }
  return minimum;
}

function flattenVector(value) {
  var x = value;
  while (Array.isArray(x) && x.length === 1 && Array.isArray(x[0])) x = x[0];
  return x;
}

function addLegend() {
  var legend = ui.Panel({style: {position: 'bottom-left', padding: '8px'}});
  legend.add(ui.Label('Land-cover classes', {fontWeight: 'bold'}));
  CLASS_VALUES.forEach(function(value, i) {
    legend.add(ui.Panel([
      ui.Label('', {backgroundColor: '#' + PALETTE[i], padding: '8px', margin: '2px'}),
      ui.Label(value + '  ' + CLASS_NAMES[i], {margin: '3px'})
    ], ui.Panel.Layout.Flow('horizontal')));
  });
  map.add(legend);
}

function showResult(best, metrics, cfg, roi) {
  state.result = best;
  state.config = cfg;
  state.running = false;
  runButton.setDisabled(false);
  exportButton.setDisabled(false);

  map.clear();
  map.centerObject(roi, 6);
  map.addLayer(best.map, {min: 1, max: 12, palette: PALETTE}, 'Land-cover classification');
  map.addLayer(roi.style({color: '111111', fillColor: '00000000', width: 2}), {}, 'AOI');
  addLegend();

  resultsPanel.clear();
  resultsPanel.add(ui.Label('Selected seed: ' + best.seed, {fontWeight: 'bold'}));
  resultsPanel.add(ui.Label('Overall accuracy: ' + (Number(metrics.overall) * 100).toFixed(2) + '%'));
  resultsPanel.add(ui.Label('Kappa: ' + Number(metrics.kappa).toFixed(3)));
  resultsPanel.add(ui.Label('Minimum included producer accuracy: ' + metrics.minimum.toFixed(2) + '%'));
  resultsPanel.add(note('Accuracy is an internal class-stratified random hold-out assessment, not independent external validation.'));
  setStatus('Mapping complete. The selected seed is ready for display/export.', '#1b5e20');
}

function run() {
  if (state.running) return;
  var cfg;
  try {
    cfg = readConfig();
    if (!cfg.aoi || !cfg.training || !cfg.classField) throw 'Asset IDs and class field are required.';
  } catch (error) {
    setStatus('Input error: ' + error, '#b71c1c');
    return;
  }

  state.running = true;
  runButton.setDisabled(true);
  exportButton.setDisabled(true);
  resultsPanel.clear();
  map.clear();
  setStatus('Loading AOI and national training points...', '#0d47a1');

  var roi = ee.FeatureCollection(cfg.aoi);
  var points = normalizedTraining(cfg);
  var geometry = points.geometry().bounds(1).union(roi.geometry().bounds(1), 1);
  var terrain = terrainImage();
  var embeddings = {};
  cfg.years.forEach(function(year) {
    var image = getEmbedding(year, geometry);
    if (year === cfg.targetYear) image = image.unmask(getEmbedding(cfg.fallbackYear, geometry));
    embeddings[year] = image;
  });

  var best = null;
  var bestMetrics = null;

  function trySeed(index) {
    if (index >= cfg.seeds.length) {
      if (best) showResult(best, bestMetrics, cfg, roi);
      else {
        state.running = false;
        runButton.setDisabled(false);
        setStatus('No valid candidate was returned. Check asset access, labels, coverage, and sample counts.', '#b71c1c');
      }
      return;
    }

    var seed = cfg.seeds[index];
    setStatus('Testing seed ' + seed + ' (' + (index + 1) + '/' + cfg.seeds.length + ')...', '#0d47a1');
    var candidate = buildCandidate(cfg, seed, roi, points, embeddings, terrain);
    ee.Dictionary({
      overall: candidate.matrix.accuracy(),
      kappa: candidate.matrix.kappa(),
      producer: candidate.matrix.producersAccuracy()
    }).evaluate(function(data, error) {
      if (error || !data) {
        trySeed(index + 1);
        return;
      }
      var producer = flattenVector(data.producer);
      var minimum = minIncludedProducer(producer, cfg.excludedThresholdClass);
      var metrics = {overall: data.overall, kappa: data.kappa, producer: producer, minimum: minimum};
      if (!best || minimum > bestMetrics.minimum) {
        best = candidate;
        bestMetrics = metrics;
      }
      if (minimum >= cfg.targetAccuracy) showResult(best, bestMetrics, cfg, roi);
      else trySeed(index + 1);
    });
  }

  trySeed(0);
}

function exportDrive() {
  if (!state.result || !state.config) {
    setStatus('Run mapping first.', '#b71c1c');
    return;
  }
  var cfg = state.config;
  var roi = ee.FeatureCollection(cfg.aoi);
  var name = cfg.prefix + '_' + cfg.targetYear + '_seed' + state.result.seed;
  Export.image.toDrive({
    image: ee.Image(state.result.map).rename('classification').toUint8(),
    description: name,
    folder: 'LandCover_Exports',
    fileNamePrefix: name,
    region: roi.geometry(),
    scale: cfg.scale,
    maxPixels: 1e13,
    fileFormat: 'GeoTIFF'
  });
  setStatus('Drive export task created. Start it from the Earth Engine Tasks tab.', '#0d47a1');
}

runButton.onClick(run);
exportButton.onClick(exportDrive);
map.setCenter(17.0, 27.0, 5);
addLegend();
