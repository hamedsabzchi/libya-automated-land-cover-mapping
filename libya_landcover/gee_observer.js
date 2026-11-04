// Read-only diagnostic companion. Does not replace functions or RUN bindings.
// prepare-reference prefixes the exact pinned reference and WP04_PROBES.
(function() {
  function finiteOrNull(value) {
    value = Number(value);
    return isFinite(value) ? value : null;
  }

  function observe() {
    if (APP.running || !APP.best || !APP.cfg || !APP.finalMap) {
      print('WP04: finish the reference RUN before capturing observations.');
      return;
    }
    var cfg = APP.cfg;
    var best = APP.best;
    var token = FLEXIBLE_RUN_STATE.token;
    var record = {
      schema_version: 'wp04.1', source: 'gee',
      gee_sha256: '1383cb783d6245031be3bce34af9ca7bc7f2952c5e02725b41f21cc75f9819e4',
      config: {
        aoi_asset: cfg.aoi, training_asset: cfg.training, class_field: cfg.classField,
        target_year: cfg.targetYear, year_count: cfg.years.length, fallback_year: cfg.fallback,
        train_fraction: cfg.trainFraction, trees: cfg.trees, target_accuracy_percent: cfg.targetAccuracy,
        excluded_class_from_threshold: cfg.excluded, bag_fraction: cfg.bag, seeds: cfg.seeds.slice(),
        scale_m: cfg.scale, tile_scale: cfg.tileScale
      },
      selection: {
        seed: best.seed, minimum_producer_percent: best.score,
        target_reached: best.score >= cfg.targetAccuracy,
        stop_reason: best.score >= cfg.targetAccuracy ? 'target_reached' : 'seeds_exhausted'
      },
      metrics: {
        overall: finiteOrNull(best.overall), kappa: finiteOrNull(best.kappa),
        producer: best.prod.map(finiteOrNull), confusion: best.conf,
        sampled_validation_count: best.conf.reduce(function(total, row) {
          return total + row.reduce(function(sum, n) { return sum + Number(n); }, 0);
        }, 0)
      },
      splits: null, raster_probes: null
    };

    function current() {
      return token === FLEXIBLE_RUN_STATE.token && APP.best === best && !APP.running;
    }
    function finish() {
      if (!current()) { print('WP04: run changed; observations discarded.'); return; }
      print('WP04 evidence JSON (copy the full string to gee-evidence.json):');
      print(JSON.stringify(record));
    }
    function raster() {
      if (!WP04_PROBES) { finish(); return; }
      var points = ee.FeatureCollection(WP04_PROBES.points.map(function(p) {
        return ee.Feature(ee.Geometry.Point([p.lon, p.lat]), {probe_id: p.id});
      }));
      var images = [{name: 'final', image: best.map}];
      cfg.years.forEach(function(y) { images.push({name: 'y' + y, image: best.yearly[y]}); });
      var bands = [];
      images.forEach(function(item) {
        var image = ee.Image(item.image);
        bands.push(image.unmask(-9999, false).rename(item.name));
        bands.push(image.mask().unmask(0, false).rename(item.name + '_mask'));
      });
      ee.Image.cat(bands).reduceRegions({collection: points, reducer: ee.Reducer.first(),
        crs: WP04_PROBES.crs, crsTransform: WP04_PROBES.transform, tileScale: 16
      }).evaluate(function(data, error) {
        if (error || !data) { print('WP04 raster observations unavailable; no complete evidence emitted.'); return; }
        record.raster_probes = {spec: WP04_PROBES, values: data.features.map(function(f) {
          return f.properties;
        }).sort(function(a, b) { return a.probe_id < b.probe_id ? -1 : a.probe_id > b.probe_id ? 1 : 0; })};
        finish();
      });
    }

    // Reuse the reference helpers for ID observation; no fitted model is rebuilt.
    var raw = ee.FeatureCollection(cfg.training);
    raw.aggregate_histogram(cfg.classField).evaluate(function(histogram, error) {
      if (error || !histogram || !current()) { print('WP04 training observations unavailable.'); return; }
      var points = flexibleNormalizeTraining(raw, cfg, flexibleBuildClassLookup(histogram).lookup);
      var split = flexibleStratified(points, cfg, best.seed);
      ee.Dictionary({normalized: points.aggregate_array('system:index').sort(),
        train: split.train.aggregate_array('system:index').sort(),
        validation: best.val.aggregate_array('system:index').sort()
      }).evaluate(function(data, splitError) {
        if (splitError || !data || !current()) { print('WP04 split observations unavailable.'); return; }
        record.splits = data;
        raster();
      });
    });
  }

  ui.root.add(ui.Button({label: 'WP04: capture execution observations', onClick: observe}));
})();
