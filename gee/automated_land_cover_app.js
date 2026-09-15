// ============================================================================
// GUIDED AUTOMATED LAND-COVER MAPPING APP
// By: Hamed Sabzchi Dehkharghani 
// Geospatial Unit - Land and Water Division (NSL)
// Food and Agriculture Organization of the United Nations (FAO HQ)
// ============================================================================

ui.root.clear();

var map = ui.Map();
map.setOptions('HYBRID');

var control = ui.Panel({style: {width: '430px', padding: '10px'}});
var resultsPanel = ui.Panel({style: {stretch: 'horizontal'}});
var downloadPanel = ui.Panel({style: {stretch: 'horizontal', margin: '8px 0'}});
var split = ui.SplitPanel(control, map, 'horizontal', false);
ui.root.add(split);

var APP = {
  running: false,
  finalMap: null,
  yearly: null,
  roi: null,
  best: null,
  cfg: null,
  downloadGeneration: 0
};

var dynamicMapSymbols = null;

var palette = [
  '#002200', '#185e0a', '#74a56a', '#fffb00', '#FF8C00', '#43BE0A',
  '#bb6d3a', '#553a17', '#808080', '#00008B', '#15c0df', '#8B4513'
];

var classValues = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12];
var classNames = [
  'Forest', 'Shrubland', 'Grassland', 'Cultivated rainfed',
  'Cultivated irrigated', 'Orchards', 'Bare soil/sand', 'Rocks', 'Built up',
  'Artificial water', 'Seasonal water', 'Sebkha'
];

var defaultSeeds = [
  42, 123, 256, 389, 512, 645, 778, 891, 999, 1111, 2222, 3333, 4444, 5555
];

function title(s) {
  return ui.Label(s, {
    fontWeight: 'bold', fontSize: '16px', margin: '10px 0 4px 0'
  });
}

function note(s) {
  return ui.Label(s, {
    fontSize: '11px', color: '#555', whiteSpace: 'pre-wrap'
  });
}

function input(label, value) {
  control.add(ui.Label(label, {fontWeight: 'bold', margin: '6px 0 1px 0'}));
  var widget = ui.Textbox({
    value: String(value), style: {stretch: 'horizontal'}
  });
  control.add(widget);
  return widget;
}

function setStatus(message, color) {
  status.setValue(message);
  status.style().set('color', color || '#333');
}

function n(value, name, min, max) {
  var number = Number(value);
  if (!isFinite(number) ||
      (min !== undefined && number < min) ||
      (max !== undefined && number > max)) {
    throw name + ' is invalid.';
  }
  return number;
}

function ints(value, name) {
  var values = String(value).split(',').map(function(item) {
    return Number(item.trim());
  }).filter(isFinite);
  if (!values.length) throw name + ' is empty.';
  return values;
}

function clean(value) {
  return String(value).trim().replace(/[^A-Za-z0-9_-]+/g, '_');
}



control.add(ui.Label('Automated Land-Cover Mapping', {
  fontWeight: 'bold', fontSize: '22px', color: '#1b5e20'
}));

control.add(note(
  'By: Hamed Sabzchi Dehkharghani - FAO-NSL Geospatial Unit; ' +
  'Food and Agriculture Organization of the United Nations'
));

control.add(title('1. Required assets'));
var aoiBox = input(
  'Area of interest FeatureCollection asset',
  'projects/practical-proxy-441422-n6/assets/Libya/Fezzan'
);
var trainBox = input(
  'Training points FeatureCollection asset',
  'projects/practical-proxy-441422-n6/assets/Libya/TD-V4'
);
var classBox = input('Class field in training points', 'lc_code');

control.add(note(
  'Training scope: ALL valid points in the training asset are used nationally, ' +
  'including points outside the AOI. Only map generation, display, and download ' +
  'are clipped to the AOI.'
));

control.add(title('2. Assessment period'));
var yearBox = input('Assessment / priority year', 2025);
var windowBox = input('Number of annual maps in temporal majority', 5);
var fallbackBox = input('Fallback year for the priority year', 2024);

control.add(title('3. Model controls'));
var targetBox = ui.Textbox({value: '60'});       // Hidden; preserved internally.
var excludedBox = ui.Textbox({value: '8'});      // Hidden; preserved internally.
var splitBox = input('Training fraction (0-1)', 0.7);
var treesBox = input('Random Forest trees', 500);
var bagBox = ui.Textbox({value: '0.95'});         // Hidden; preserved internally.
var seedsBox = ui.Textbox({value: defaultSeeds.join(',')}); // Hidden.
var scaleBox = input('Processing/download scale (m)', 10);
var tileScaleBox = ui.Textbox({value: '16'});     // Hidden; preserved internally.

control.add(title('4. Download controls'));
var prefixBox = input('Download file name prefix', 'landcover_automated');
var rowsBox = input('Tile rows for large-area download', 2);
var colsBox = input('Tile columns for large-area download', 5);

control.add(note(
  'The published App generates direct GeoTIFF download links. No Earth Engine ' +
  'Tasks panel is needed. For a large AOI, use tiled downloads. The selected Random Forest models are converted to fixed decision trees before ' +
  'download. Oversized tiles are automatically divided until valid links are created. ' +
  'After downloading, the user may save or upload the files to Google Drive.'
));

var status = ui.Label('Ready.', {
  fontWeight: 'bold', whiteSpace: 'pre-wrap', margin: '10px 0'
});
control.add(status);

var runButton = ui.Button({
  label: 'RUN AUTOMATED MAPPING',
  style: {
    stretch: 'horizontal', color: 'black', backgroundColor: '#2e7d32'
  }
});

var exportButton = ui.Button({
  label: 'GENERATE FULL-MAP DOWNLOAD',
  disabled: true,
  style: {
    stretch: 'horizontal', color: 'black', backgroundColor: '#1565c0'
  }
});

var tileButton = ui.Button({
  label: 'GENERATE TILED DOWNLOADS',
  disabled: true,
  style: {
    stretch: 'horizontal', color: 'black', backgroundColor: '#6a1b9a'
  }
});

control.add(runButton);
control.add(exportButton);
control.add(tileButton);
control.add(downloadPanel);
control.add(title('5. Results'));
control.add(resultsPanel);



function readConfig() {
  var target = n(yearBox.getValue(), 'Assessment year', 2017, 2100);
  var count = Math.round(n(windowBox.getValue(), 'Year count', 1, 20));
  var years = [];
  for (var i = 0; i < count; i++) years.push(target - i);

  return {
    aoi: aoiBox.getValue().trim(),
    training: trainBox.getValue().trim(),
    classField: classBox.getValue().trim(),
    targetYear: target,
    years: years,
    fallback: Math.round(n(
      fallbackBox.getValue(), 'Fallback year', 2017, 2100
    )),
    targetAccuracy: n(targetBox.getValue(), 'Target accuracy', 0, 100),
    excluded: Math.round(n(
      excludedBox.getValue(), 'Excluded class', -999, 999
    )),
    trainFraction: n(splitBox.getValue(), 'Training fraction', 0.01, 0.99),
    trees: Math.round(n(treesBox.getValue(), 'Trees', 1, 5000)),
    bag: n(bagBox.getValue(), 'Bag fraction', 0.01, 1),
    seeds: ints(seedsBox.getValue(), 'Seeds'),
    scale: n(scaleBox.getValue(), 'Scale', 1, 10000),
    tileScale: Math.round(n(tileScaleBox.getValue(), 'tileScale', 1, 64)),
    prefix: clean(prefixBox.getValue()),
    rows: Math.round(n(rowsBox.getValue(), 'Rows', 1, 100)),
    cols: Math.round(n(colsBox.getValue(), 'Columns', 1, 100))
  };
}

function getEmbedding(year, roi) {
  var start = ee.Date.fromYMD(year, 1, 1);
  return ee.ImageCollection('GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL')
    .filterDate(start, start.advance(1, 'year'))
    .filterBounds(roi)
    .mosaic();
}

function buildInputs(cfg, processingGeometry) {
  var output = {};
  cfg.years.forEach(function(year) {
    var embedding = getEmbedding(year, processingGeometry);
    if (year === cfg.targetYear) {
      embedding = embedding.unmask(
        getEmbedding(cfg.fallback, processingGeometry)
      );
    }
    output[year] = embedding;
  });
  return output;
}

function stratified(points, cfg, seed) {
  var classes = points.aggregate_array(cfg.classField).distinct();
  var splits = classes.map(function(classValue) {
    var classPoints = points
      .filter(ee.Filter.eq(cfg.classField, ee.Number(classValue)))
      .randomColumn('random', seed);
    return ee.Dictionary({
      train: classPoints.filter(ee.Filter.lt('random', cfg.trainFraction)),
      val: classPoints.filter(ee.Filter.gte('random', cfg.trainFraction))
    });
  });

  return {
    train: ee.FeatureCollection(splits.map(function(item) {
      return ee.Dictionary(item).get('train');
    })).flatten(),
    val: ee.FeatureCollection(splits.map(function(item) {
      return ee.Dictionary(item).get('val');
    })).flatten()
  };
}

function makeMap(train, cfg, seed, roi, embeddings, terrain) {
  var yearly = {};
  var yearlyForValidation = {};
  var classifiers = {};

  cfg.years.forEach(function(year) {
    var image = ee.Image.cat([embeddings[year], terrain]);
    var samples = image.sampleRegions({
      collection: train,
      properties: [cfg.classField],
      scale: cfg.scale,
      tileScale: cfg.tileScale,
      geometries: false
    }).filter(ee.Filter.notNull(image.bandNames()));

    var classifier = ee.Classifier.smileRandomForest({
      numberOfTrees: cfg.trees,
      bagFraction: cfg.bag,
      seed: seed
    }).train({
      features: samples,
      classProperty: cfg.classField,
      inputProperties: image.bandNames()
    });

    classifiers[year] = classifier;
    yearlyForValidation[year] = image.classify(classifier).rename('c' + year);
    yearly[year] = yearlyForValidation[year].clip(roi);
  });

  function temporalDecision(yearlyDictionary) {
    var stack = ee.Image.cat(cfg.years.map(function(year) {
      return yearlyDictionary[year].rename('y' + year);
    }));

    var priority = stack.select('y' + cfg.targetYear);
    var standard = stack.reduce(ee.Reducer.mode());
    var class4Count = ee.Image(0);
    var class5Count = ee.Image(0);

    cfg.years.forEach(function(year) {
      class4Count = class4Count.add(stack.select('y' + year).eq(4));
      class5Count = class5Count.add(stack.select('y' + year).eq(5));
    });

    return standard
      .where(priority.eq(4).or(priority.eq(5)), priority)
      .where(class5Count.gte(2), 5)
      .where(class4Count.gte(2), 4)
      .where(class4Count.gte(2).and(class5Count.gte(2)), priority)
      .rename('classification');
  }

  var nationalValidationMap = temporalDecision(yearlyForValidation);
  var finalMap = nationalValidationMap.clip(roi);

  return {
    finalMap: finalMap,
    validationMap: nationalValidationMap,
    yearly: yearly,
    classifiers: classifiers
  };
}



function temporalDecisionFromYearly(yearlyDictionary, cfg) {
  var stack = ee.Image.cat(cfg.years.map(function(year) {
    return yearlyDictionary[year].rename('y' + year);
  }));
  var priority = stack.select('y' + cfg.targetYear);
  var standard = stack.reduce(ee.Reducer.mode());
  var class4Count = ee.Image(0);
  var class5Count = ee.Image(0);
  cfg.years.forEach(function(year) {
    class4Count = class4Count.add(stack.select('y' + year).eq(4));
    class5Count = class5Count.add(stack.select('y' + year).eq(5));
  });
  return standard
    .where(priority.eq(4).or(priority.eq(5)), priority)
    .where(class5Count.gte(2), 5)
    .where(class4Count.gte(2), 4)
    .where(class4Count.gte(2).and(class5Count.gte(2)), priority)
    .rename('classification');
}

function materializeBestModel(best, cfg, roi, embeddings, terrain) {
  setStatus(
    'Preparing the selected model for reliable downloads...',
    '#0d47a1'
  );

  var treeDictionary = {};
  cfg.years.forEach(function(year) {
    treeDictionary[String(year)] = best.classifiers[year]
      .explain()
      .get('trees');
  });

  ee.Dictionary(treeDictionary).evaluate(function(treeData, treeError) {
    if (treeError || !treeData) {
      APP.running = false;
      runButton.setDisabled(false);
      setStatus(
        'The selected Random Forest model could not be prepared: ' +
        lcErrorText(treeError || 'No decision trees were returned.'),
        '#b71c1c'
      );
      return;
    }

    var lightweightYearlyNational = {};
    var lightweightYearlyAOI = {};

    cfg.years.forEach(function(year) {
      var trees = treeData[String(year)];
      var fixedClassifier = ee.Classifier.decisionTreeEnsemble(trees);
      var predictorImage = ee.Image.cat([embeddings[year], terrain]);
      var classified = predictorImage
        .classify(fixedClassifier)
        .rename('c' + year);
      lightweightYearlyNational[year] = classified;
      lightweightYearlyAOI[year] = classified.clip(roi);
    });

    best.map = temporalDecisionFromYearly(
      lightweightYearlyNational, cfg
    ).clip(roi);
    best.yearly = lightweightYearlyAOI;
    best.classifiers = null;

    finish(best, cfg, roi);
  });
}



function legend() {
  var panel = ui.Panel({
    style: {position: 'bottom-left', padding: '8px'}
  });
  panel.add(ui.Label('Land Cover Classes', {fontWeight: 'bold'}));
  classValues.forEach(function(value, index) {
    panel.add(ui.Panel([
      ui.Label('', {
        backgroundColor: palette[index], padding: '8px', margin: '2px'
      }),
      ui.Label(value + '  ' + classNames[index], {margin: '3px'})
    ], ui.Panel.Layout.Flow('horizontal')));
  });
  map.add(panel);
}

function lcTableCell(value, width, isHeader, alignLeft) {
  return ui.Label(String(value), {
    width: width,
    padding: '6px 4px',
    margin: '0',
    backgroundColor: isHeader ? '#1b5e20' : '#ffffff',
    color: isHeader ? '#ffffff' : '#222222',
    fontWeight: isHeader ? 'bold' : 'normal',
    textAlign: alignLeft ? 'left' : 'center',
    border: '1px solid #bdbdbd'
  });
}

function lcTableRow(values, widths, isHeader) {
  var widgets = [];
  values.forEach(function(value, index) {
    widgets.push(lcTableCell(value, widths[index], isHeader, index === 1));
  });
  return ui.Panel(widgets, ui.Panel.Layout.Flow('horizontal'), {
    margin: '0', padding: '0'
  });
}

function showResults(best, cfg) {
  resultsPanel.clear();
  var overallText = (best.overall * 100).toFixed(2);
  var kappaText = best.kappa.toFixed(3);

  resultsPanel.add(ui.Label(
    'Best seed: ' + best.seed + ' | Overall accuracy: ' + overallText +
    '% | Kappa: ' + kappaText,
    {fontWeight: 'bold', whiteSpace: 'pre-wrap', margin: '4px 0 8px 0'}
  ));

  var features = [];
  var records = [];

  for (var i = 0; i < classValues.length; i++) {
    var matrixRow = best.conf[i] || [];
    var sampleCount = matrixRow.reduce(function(sum, value) {
      return sum + Number(value || 0);
    }, 0);

    var columnTotal = 0;
    for (var j = 0; j < best.conf.length; j++) {
      columnTotal += Number((best.conf[j] || [])[i] || 0);
    }

    var producerAccuracy = Number(best.prod[i] || 0) * 100;
    var userAccuracy = columnTotal > 0 ?
      Number(matrixRow[i] || 0) / columnTotal * 100 : 0;

    var record = {
      code: classValues[i],
      name: classNames[i],
      producer: producerAccuracy,
      user: userAccuracy,
      samples: sampleCount,
      status: classValues[i] === cfg.excluded ? 'Excluded' : 'Included'
    };

    records.push(record);
    features.push(ee.Feature(null, {
      Name: record.name,
      Producer: record.producer,
      User: record.user,
      Samples: record.samples
    }));
  }

  var accuracyFeatures = ee.FeatureCollection(features);

  resultsPanel.add(ui.Chart.feature.byFeature(
    accuracyFeatures, 'Name', ['Producer', 'User'])
    .setChartType('ColumnChart')
    .setOptions({
      title: 'Producer and User Accuracy by Class (%)',
      vAxis: {minValue: 0, maxValue: 100},
      legend: {position: 'top'},
      hAxis: {slantedText: true, slantedTextAngle: 45}
    }));

  resultsPanel.add(ui.Chart.feature.byFeature(
    accuracyFeatures, 'Name', ['Samples'])
    .setChartType('ColumnChart')
    .setOptions({
      title: 'Validation Samples by Reference Class',
      legend: {position: 'none'},
      hAxis: {slantedText: true, slantedTextAngle: 45}
    }));

  resultsPanel.add(ui.Label('Class Accuracy Table', {
    fontWeight: 'bold', fontSize: '14px', margin: '10px 0 3px 0'
  }));

  var accuracyWidths = ['42px', '132px', '67px', '67px', '54px', '62px'];
  var accuracyTable = ui.Panel({
    style: {margin: '0 0 10px 0', padding: '0'}
  });

  accuracyTable.add(lcTableRow(
    ['Code', 'Land-cover class', 'Producer', 'User', 'N', 'Status'],
    accuracyWidths,
    true
  ));

  records.forEach(function(record) {
    accuracyTable.add(lcTableRow([
      record.code,
      record.name,
      record.producer.toFixed(2) + '%',
      record.user.toFixed(2) + '%',
      record.samples,
      record.status
    ], accuracyWidths, false));
  });
  resultsPanel.add(accuracyTable);

  resultsPanel.add(ui.Label(
    'Confusion Matrix: rows = reference, columns = mapped',
    {fontWeight: 'bold', fontSize: '14px', margin: '8px 0 3px 0'}
  ));

  var matrixWidths = ['62px'];
  classValues.forEach(function() { matrixWidths.push('27px'); });
  var matrixTable = ui.Panel({style: {margin: '0', padding: '0'}});
  matrixTable.add(lcTableRow(
    ['Ref/Map'].concat(classValues), matrixWidths, true
  ));

  best.conf.forEach(function(matrixRow, rowIndex) {
    matrixTable.add(lcTableRow(
      [classValues[rowIndex]].concat(matrixRow), matrixWidths, false
    ));
  });
  resultsPanel.add(matrixTable);
}

function finish(best, cfg, roi) {
  APP.finalMap = best.map;
  APP.yearly = best.yearly;
  APP.roi = roi;
  APP.best = best;
  APP.cfg = cfg;

  map.clear();
  map.centerObject(roi, 8);
  map.addLayer(roi, {color: 'red'}, 'AOI', false);

  var visualization = {min: 1, max: 12, palette: palette};
  cfg.years.forEach(function(year) {
    map.addLayer(best.yearly[year], visualization, String(year), false);
  });
  map.addLayer(best.map, visualization, 'FINAL ' + cfg.targetYear, true);

  legend();
  dynamicMapSymbols = addDynamicMapSymbols(map);
  showResults(best, cfg);

  exportButton.setDisabled(false);
  tileButton.setDisabled(false);
  runButton.setDisabled(false);
  APP.running = false;

  setStatus(
    'Complete. Best seed ' + best.seed +
    '. Review the results, then generate the full-map or tiled GeoTIFF downloads.',
    '#1b5e20'
  );
}

function run() {
  if (APP.running) return;

  var cfg;
  try {
    cfg = readConfig();
  } catch (error) {
    setStatus('Input error: ' + error, '#b71c1c');
    return;
  }

  APP.running = true;
  APP.downloadGeneration++;
  runButton.setDisabled(true);
  exportButton.setDisabled(true);
  tileButton.setDisabled(true);
  resultsPanel.clear();
  downloadPanel.clear();
  map.clear();

  setStatus(
    'Loading national training data and AOI mapping inputs...', '#0d47a1'
  );

  var roi = ee.FeatureCollection(cfg.aoi);
  var raw = ee.FeatureCollection(cfg.training);
  var points = raw.map(function(feature) {
    return feature.set(
      cfg.classField,
      ee.Number.parse(ee.String(feature.get(cfg.classField)))
    );
  }).filter(ee.Filter.inList(cfg.classField, classValues));

  var nationalTrainingGeometry = points.geometry().bounds(1);
  var processingGeometry = nationalTrainingGeometry.union(
    roi.geometry().bounds(1), 1
  );

  var dem = ee.Image('USGS/SRTMGL1_003');
  var terrain = ee.Image.cat([
    dem.select('elevation'),
    ee.Terrain.slope(dem),
    ee.Terrain.aspect(dem)
  ]).rename(['elevation', 'slope', 'aspect']);

  var embeddings = buildInputs(cfg, processingGeometry);
  var best = null;

  print('National training points before split:', points.size());
  print(
    'AOI training points (diagnostic only, not used to filter training):',
    points.filterBounds(roi).size()
  );
  print(
    'Outside-AOI training points retained:',
    points.filterBounds(roi).size().multiply(-1).add(points.size())
  );

  function attempt(index) {
    if (index >= cfg.seeds.length) {
      if (best) {
        materializeBestModel(best, cfg, roi, embeddings, terrain);
      } else {
        APP.running = false;
        runButton.setDisabled(false);
        setStatus(
          'No valid result was returned. Check national training assets, ' +
          'class fields, embedding coverage, and sample counts.',
          '#b71c1c'
        );
      }
      return;
    }

    var seed = cfg.seeds[index];
    setStatus(
      'Testing national seed ' + seed + ' (' +
      (index + 1) + ' of ' + cfg.seeds.length + ')...',
      '#0d47a1'
    );

    var splitData = stratified(points, cfg, seed);
    var result = makeMap(
      splitData.train, cfg, seed, roi, embeddings, terrain
    );

    var validation = result.validationMap.sampleRegions({
      collection: splitData.val,
      properties: [cfg.classField],
      scale: cfg.scale,
      tileScale: cfg.tileScale,
      geometries: false
    });

    var errorMatrix = validation.errorMatrix(
      cfg.classField, 'classification', classValues
    );

    ee.Dictionary({
      overall: errorMatrix.accuracy(),
      kappa: errorMatrix.kappa(),
      prod: errorMatrix.producersAccuracy(),
      conf: errorMatrix.array()
    }).evaluate(function(data, evaluationError) {
      if (evaluationError || !data) {
        setStatus(
          'Seed ' + seed + ' failed; continuing automatically.', '#e65100'
        );
        attempt(index + 1);
        return;
      }

      var producer = Array.isArray(data.prod) ?
        data.prod : Object.values(data.prod);
      if (producer.length === 1 && Array.isArray(producer[0])) {
        producer = producer[0];
      }

      var confusion = Array.isArray(data.conf) ?
        data.conf : Object.values(data.conf);
      if (confusion.length === 1 &&
          Array.isArray(confusion[0]) &&
          Array.isArray(confusion[0][0])) {
        confusion = confusion[0];
      }

      var minimumAccuracy = 100;
      var targetReached = true;

      for (var k = 0; k < producer.length; k++) {
        var accuracy = Number(producer[k]) * 100;
        if (classValues[k] !== cfg.excluded) {
          minimumAccuracy = Math.min(minimumAccuracy, accuracy);
          if (accuracy < cfg.targetAccuracy) targetReached = false;
        }
      }

      if (!best || minimumAccuracy > best.score) {
        best = {
          score: minimumAccuracy,
          seed: seed,
          map: result.finalMap,
          yearly: result.yearly,
          overall: Number(data.overall),
          kappa: Number(data.kappa),
          prod: producer,
          conf: confusion,
          val: splitData.val,
          classifiers: result.classifiers
        };
      }

      if (targetReached) {
        materializeBestModel(best, cfg, roi, embeddings, terrain);
      } else {
        attempt(index + 1);
      }
    });
  }

  attempt(0);
}

runButton.onClick(run);



function lcRequireCompletedMap() {
  if (!APP.finalMap || !APP.roi || !APP.cfg) {
    setStatus(
      'Run the automated mapping first. Download buttons become active after ' +
      'a final map is available.',
      '#b71c1c'
    );
    return false;
  }
  return true;
}

function lcAddDownloadHeading(heading, explanation) {
  downloadPanel.add(ui.Label(heading, {
    fontWeight: 'bold',
    fontSize: '14px',
    color: '#0d47a1',
    margin: '8px 0 3px 0'
  }));
  if (explanation) {
    downloadPanel.add(ui.Label(explanation, {
      fontSize: '11px',
      color: '#555555',
      whiteSpace: 'pre-wrap',
      margin: '0 0 6px 0'
    }));
  }
}

function lcAddDownloadLink(label, url, details) {
  downloadPanel.add(ui.Label({
    value: label,
    targetUrl: url,
    style: {
      color: '#0b57d0',
      fontWeight: 'bold',
      textDecoration: 'underline',
      whiteSpace: 'pre-wrap',
      margin: '4px 0 1px 0'
    }
  }));

  if (details) {
    downloadPanel.add(ui.Label(details, {
      fontSize: '10px',
      color: '#666666',
      whiteSpace: 'pre-wrap',
      margin: '0 0 5px 0'
    }));
  }
}

function lcErrorText(error) {
  var message;
  if (error && error.message) {
    message = error.message;
  } else if (error !== undefined && error !== null && String(error)) {
    message = String(error);
  } else {
    message = 'Unknown download-generation error.';
  }
  return message
    .replace(/<br\s*\/?>/gi, '\n')
    .replace(/<[^>]+>/g, '');
}

function lcAddDownloadError(itemName, error) {
  downloadPanel.add(ui.Label(
    itemName + ': the download link could not be generated.\n' +
    lcErrorText(error) + '\n' +
    'For a large area, increase the tile rows and columns and try again.',
    {
      color: '#b71c1c',
      fontSize: '11px',
      whiteSpace: 'pre-wrap',
      margin: '4px 0 7px 0',
      padding: '5px',
      border: '1px solid #ef9a9a'
    }
  ));
}

function lcRequestGeoTiffUrl(
  image, name, region, cfg, generationId, onSuccess, onFailure
) {
  var preparedImage = ee.Image(image)
    .rename('classification')
    .toInt8();

  var parameters = {
    name: name,
    scale: cfg.scale,
    crs: 'EPSG:4326',
    region: region,
    filePerBand: false,
    format: 'GEO_TIFF'
  };

  try {
    preparedImage.getDownloadURL(parameters, function(url, error) {
      if (generationId !== APP.downloadGeneration) return;
      if (error || !url) {
        onFailure(error || 'No download URL was returned.');
        return;
      }
      onSuccess(url);
    });
  } catch (requestError) {
    if (generationId !== APP.downloadGeneration) return;
    onFailure(requestError);
  }
}

exportButton.onClick(function() {
  if (!lcRequireCompletedMap()) return;

  exportButton.setDisabled(true);
  tileButton.setDisabled(true);
  APP.downloadGeneration++;
  var generationId = APP.downloadGeneration;
  downloadPanel.clear();

  var cfg = APP.cfg;
  var name = cfg.prefix + '_' + cfg.targetYear + '_' +
    cfg.scale + 'm_full_AOI';

  lcAddDownloadHeading(
    'Full-map GeoTIFF download',
    'Generating a direct browser-download link. If the full AOI is too large, ' +
    'use the tiled-download option.'
  );

  setStatus('Generating the full-map GeoTIFF download link...', '#0d47a1');

  lcRequestGeoTiffUrl(
    APP.finalMap,
    name,
    APP.roi.geometry(),
    cfg,
    generationId,
    function(url) {
      downloadPanel.clear();
      lcAddDownloadHeading(
        'Full-map GeoTIFF download',
        'Click the link below. The browser will download the raster directly.'
      );
      lcAddDownloadLink(
        'DOWNLOAD FULL MAP: ' + name + '.tif',
        url,
        'Single-band Int8 GeoTIFF; classes 1-12; scale: ' +
        cfg.scale + ' m; CRS: EPSG:4326.'
      );
      setStatus(
        'Full-map download link is ready. Click the link above.', '#1b5e20'
      );
      exportButton.setDisabled(false);
      tileButton.setDisabled(false);
    },
    function(error) {
      downloadPanel.clear();
      lcAddDownloadHeading(
        'Full-map GeoTIFF download',
        'The full AOI could not be prepared as one direct download.'
      );
      lcAddDownloadError(name, error);
      downloadPanel.add(ui.Label(
        'Use GENERATE TILED DOWNLOADS. If a tile fails, increase the numbers ' +
        'of rows and columns.',
        {
          color: '#e65100',
          fontWeight: 'bold',
          fontSize: '11px',
          whiteSpace: 'pre-wrap',
          margin: '5px 0'
        }
      ));
      setStatus(
        'The full AOI is too large or could not be prepared as one direct ' +
        'download. Use tiled downloads.',
        '#e65100'
      );
      exportButton.setDisabled(false);
      tileButton.setDisabled(false);
    }
  );
});

tileButton.onClick(function() {
  if (!lcRequireCompletedMap()) return;

  exportButton.setDisabled(true);
  tileButton.setDisabled(true);
  APP.downloadGeneration++;
  var generationId = APP.downloadGeneration;
  downloadPanel.clear();

  var cfg = APP.cfg;
  var roiGeometry = APP.roi.geometry();
  var MAX_SPLIT_DEPTH = 9;

  setStatus('Building the initial download grid...', '#0d47a1');
  lcAddDownloadHeading(
    'Tiled GeoTIFF downloads',
    'Building an initial ' + cfg.rows + ' row x ' + cfg.cols +
    ' column grid. Any oversized tile will be divided automatically.'
  );

  var ring = ee.List(roiGeometry.bounds().coordinates().get(0));
  var lower = ee.List(ring.get(0));
  var upper = ee.List(ring.get(2));
  var xMin = ee.Number(lower.get(0));
  var yMin = ee.Number(lower.get(1));
  var xMax = ee.Number(upper.get(0));
  var yMax = ee.Number(upper.get(1));
  var width = xMax.subtract(xMin).divide(cfg.cols);
  var height = yMax.subtract(yMin).divide(cfg.rows);

  var grid = ee.FeatureCollection(
    ee.List.sequence(0, cfg.rows - 1).map(function(rowIndex) {
      return ee.List.sequence(0, cfg.cols - 1).map(function(colIndex) {
        rowIndex = ee.Number(rowIndex);
        colIndex = ee.Number(colIndex);
        var x0 = xMin.add(width.multiply(colIndex));
        var y0 = yMin.add(height.multiply(rowIndex));
        var rectangle = ee.Geometry.Rectangle([
          x0, y0, x0.add(width), y0.add(height)
        ], null, false);
        var clippedCell = rectangle.intersection(roiGeometry, 1);
        return ee.Feature(clippedCell, {
          row: rowIndex,
          col: colIndex,
          tile: rowIndex.multiply(cfg.cols).add(colIndex).add(1),
          area_m2: clippedCell.area(1)
        });
      });
    }).flatten()
  ).filter(ee.Filter.gt('area_m2', 0));

  map.addLayer(grid.style({
    color: 'FF5733', width: 2, fillColor: '00000000'
  }), {}, 'Initial download grid', false);

  function isSizeLimitError(error) {
    var message = lcErrorText(error).toLowerCase();
    return message.indexOf('request size') >= 0 ||
      message.indexOf('pixel grid dimensions') >= 0 ||
      message.indexOf('too many pixels') >= 0 ||
      message.indexOf('must be less than or equal') >= 0 ||
      message.indexOf('exceeds') >= 0 ||
      message.indexOf('memory limit') >= 0;
  }

  function splitItemIntoFour(item, callback, failureCallback) {
    var geometry = ee.Geometry(item.geometry);
    var boundsRing = ee.List(geometry.bounds(1).coordinates().get(0));
    var lowerCorner = ee.List(boundsRing.get(0));
    var upperCorner = ee.List(boundsRing.get(2));
    var xmin = ee.Number(lowerCorner.get(0));
    var ymin = ee.Number(lowerCorner.get(1));
    var xmax = ee.Number(upperCorner.get(0));
    var ymax = ee.Number(upperCorner.get(1));
    var xmid = xmin.add(xmax).divide(2);
    var ymid = ymin.add(ymax).divide(2);

    var rectangles = ee.List([
      ee.Geometry.Rectangle([xmin, ymin, xmid, ymid], null, false),
      ee.Geometry.Rectangle([xmid, ymin, xmax, ymid], null, false),
      ee.Geometry.Rectangle([xmin, ymid, xmid, ymax], null, false),
      ee.Geometry.Rectangle([xmid, ymid, xmax, ymax], null, false)
    ]);

    var children = ee.FeatureCollection(
      ee.List.sequence(0, 3).map(function(childIndex) {
        childIndex = ee.Number(childIndex);
        var childGeometry = ee.Geometry(rectangles.get(childIndex))
          .intersection(geometry, 1);
        return ee.Feature(childGeometry, {
          child: childIndex.add(1),
          area_m2: childGeometry.area(1)
        });
      })
    ).filter(ee.Filter.gt('area_m2', 0));

    children.evaluate(function(collection, splitError) {
      if (generationId !== APP.downloadGeneration) return;
      if (splitError || !collection || !collection.features ||
          !collection.features.length) {
        failureCallback(splitError || 'Automatic subdivision returned no valid child tiles.');
        return;
      }

      var output = collection.features.map(function(feature) {
        var childNumber = feature.properties.child;
        return {
          geometry: feature.geometry,
          rootTile: item.rootTile,
          path: item.path + '_' + childNumber,
          depth: item.depth + 1
        };
      });
      callback(output);
    });
  }

  grid.evaluate(function(collection, gridError) {
    if (generationId !== APP.downloadGeneration) return;

    if (gridError || !collection || !collection.features) {
      downloadPanel.clear();
      lcAddDownloadHeading(
        'Tiled GeoTIFF downloads', 'The download grid could not be created.'
      );
      lcAddDownloadError(
        'Download grid', gridError || 'No grid features were returned.'
      );
      setStatus(
        'Tile-grid error. Check the AOI geometry and tile settings.', '#b71c1c'
      );
      exportButton.setDisabled(false);
      tileButton.setDisabled(false);
      return;
    }

    var initialFeatures = collection.features;
    var queue = initialFeatures.map(function(feature, index) {
      var properties = feature.properties || {};
      return {
        geometry: feature.geometry,
        rootTile: properties.tile !== undefined ? properties.tile : index + 1,
        path: '',
        depth: 0
      };
    });

    downloadPanel.clear();
    lcAddDownloadHeading(
      'Tiled GeoTIFF downloads',
      initialFeatures.length + ' initial AOI tiles were identified. Oversized ' +
      'tiles are automatically divided. Each successful link represents one ' +
      'non-overlapping part of the final map.'
    );

    if (!queue.length) {
      downloadPanel.add(ui.Label('No non-empty tile intersects the AOI.', {
        color: '#b71c1c', fontWeight: 'bold'
      }));
      setStatus('No non-empty tile intersects the AOI.', '#b71c1c');
      exportButton.setDisabled(false);
      tileButton.setDisabled(false);
      return;
    }

    var successful = 0;
    var failed = 0;
    var subdivisions = 0;
    var processed = 0;

    function finishDownloads() {
      exportButton.setDisabled(false);
      tileButton.setDisabled(false);
      if (failed === 0) {
        setStatus(
          successful + ' GeoTIFF download links are ready. ' +
          subdivisions + ' automatic subdivisions were applied. ' +
          'Click each download link above.',
          '#1b5e20'
        );
      } else {
        setStatus(
          successful + ' download links are ready; ' + failed +
          ' part(s) could not be generated. Increase the initial rows and ' +
          'columns if needed and try again.',
          '#e65100'
        );
      }
    }

    function processNextItem() {
      if (generationId !== APP.downloadGeneration) return;
      if (!queue.length) {
        finishDownloads();
        return;
      }

      var item = queue.shift();
      processed++;
      var suffix = item.path || '';
      var tileId = String(item.rootTile) + suffix;
      var tileName = cfg.prefix + '_' + cfg.targetYear + '_' +
        cfg.scale + 'm_tile_' + tileId;
      var tileGeometry = ee.Geometry(item.geometry);

      setStatus(
        'Preparing download part ' + (successful + 1) +
        '. Remaining queue: ' + queue.length +
        '. Automatic subdivisions: ' + subdivisions + '.',
        '#0d47a1'
      );

      lcRequestGeoTiffUrl(
        APP.finalMap.clip(tileGeometry),
        tileName,
        tileGeometry,
        cfg,
        generationId,
        function(url) {
          successful++;
          lcAddDownloadLink(
            'DOWNLOAD PART ' + successful + ': ' + tileName + '.tif',
            url,
            'Initial tile ' + item.rootTile +
            (item.depth ? '; automatic subdivision level ' + item.depth : '') +
            '; scale: ' + cfg.scale + ' m; CRS: EPSG:4326.'
          );
          processNextItem();
        },
        function(error) {
          if (isSizeLimitError(error) && item.depth < MAX_SPLIT_DEPTH) {
            subdivisions++;
            setStatus(
              'An oversized tile was detected and is being divided ' +
              'automatically. Subdivision level ' + (item.depth + 1) + '.',
              '#0d47a1'
            );
            splitItemIntoFour(
              item,
              function(children) {
                for (var childIndex = children.length - 1;
                     childIndex >= 0; childIndex--) {
                  queue.unshift(children[childIndex]);
                }
                processNextItem();
              },
              function(splitError) {
                failed++;
                lcAddDownloadError(tileName, splitError);
                processNextItem();
              }
            );
          } else {
            failed++;
            lcAddDownloadError(tileName, error);
            processNextItem();
          }
        }
      );
    }

    processNextItem();
  });
});


function addDynamicMapSymbols(mapWidget) {
  if (!mapWidget) throw new Error('A valid ui.Map must be supplied.');

  mapWidget.setControlVisibility({
    all: false,
    layerList: true,
    mapTypeControl: true
  });

  var TARGET_BAR_PIXELS = 180;
  var MIN_BAR_PIXELS = 100;
  var MAX_BAR_PIXELS = 240;
  var SEGMENT_COUNT = 4;

  if (dynamicMapSymbols && dynamicMapSymbols.remove) {
    try {
      dynamicMapSymbols.remove();
    } catch (ignorePreviousSymbolsError) {}
  }

  var mainPanel = ui.Panel({
    layout: ui.Panel.Layout.flow('vertical'),
    style: {
      position: 'bottom-right',
      margin: '10px',
      padding: '8px 10px',
      backgroundColor: '#ffffff',
      border: '1px solid #777777'
    }
  });

  var northArrow = ui.Label({
    value: '▲\nN',
    style: {
      width: '30px',
      fontSize: '18px',
      fontWeight: 'bold',
      color: '#111111',
      textAlign: 'center',
      whiteSpace: 'pre',
      margin: '0 10px 0 0',
      padding: '0'
    }
  });

  var barPanel = ui.Panel({
    layout: ui.Panel.Layout.flow('horizontal'),
    style: {margin: '0', padding: '0', height: '12px'}
  });

  var labelPanel = ui.Panel({
    layout: ui.Panel.Layout.flow('horizontal'),
    style: {margin: '1px 0 0 0', padding: '0'}
  });

  var scalePanel = ui.Panel({
    widgets: [barPanel, labelPanel],
    layout: ui.Panel.Layout.flow('vertical'),
    style: {margin: '0', padding: '0'}
  });

  var symbolRow = ui.Panel({
    widgets: [northArrow, scalePanel],
    layout: ui.Panel.Layout.flow('horizontal'),
    style: {margin: '0', padding: '0'}
  });

  mainPanel.add(symbolRow);
  mapWidget.add(mainPanel);

  function chooseNiceDistance(rawMetres) {
    if (!isFinite(rawMetres) || rawMetres <= 0) return 1000;
    var power = Math.pow(10, Math.floor(Math.log(rawMetres) / Math.LN10));
    var normalized = rawMetres / power;
    var multiplier;
    if (normalized <= 1) multiplier = 1;
    else if (normalized <= 2) multiplier = 2;
    else if (normalized <= 5) multiplier = 5;
    else multiplier = 10;
    return multiplier * power;
  }

  function formatDistance(metres) {
    if (metres >= 1000) {
      var kilometres = metres / 1000;
      var roundedKilometres = kilometres >= 10 ?
        Math.round(kilometres) : Math.round(kilometres * 10) / 10;
      return roundedKilometres + ' km';
    }
    if (metres >= 10) return Math.round(metres) + ' m';
    return Math.round(metres * 10) / 10 + ' m';
  }

  function makeSegment(widthPixels, dark) {
    return ui.Label({
      value: '',
      style: {
        width: widthPixels + 'px',
        height: '10px',
        margin: '0',
        padding: '0',
        backgroundColor: dark ? '#111111' : '#ffffff',
        border: '1px solid #111111'
      }
    });
  }

  function makeLabel(text, widthPixels, alignment) {
    return ui.Label({
      value: text,
      style: {
        width: widthPixels + 'px',
        fontSize: '9px',
        color: '#111111',
        textAlign: alignment,
        whiteSpace: 'nowrap',
        margin: '0',
        padding: '0'
      }
    });
  }

  function updateScaleBar() {
    try {
      var metresPerPixel = Number(mapWidget.getScale());
      if (!isFinite(metresPerPixel) || metresPerPixel <= 0) return;

      var desiredMetres = metresPerPixel * TARGET_BAR_PIXELS;
      var niceMetres = chooseNiceDistance(desiredMetres);
      var totalPixels = Math.round(niceMetres / metresPerPixel);

      if (totalPixels < MIN_BAR_PIXELS) {
        niceMetres = chooseNiceDistance(
          metresPerPixel * TARGET_BAR_PIXELS * 1.5
        );
        totalPixels = Math.round(niceMetres / metresPerPixel);
      }

      if (totalPixels > MAX_BAR_PIXELS) {
        niceMetres = chooseNiceDistance(
          metresPerPixel * TARGET_BAR_PIXELS * 0.6
        );
        totalPixels = Math.round(niceMetres / metresPerPixel);
      }

      totalPixels = Math.max(
        MIN_BAR_PIXELS, Math.min(MAX_BAR_PIXELS, totalPixels)
      );
      var segmentPixels = Math.max(
        1, Math.floor(totalPixels / SEGMENT_COUNT)
      );
      var correctedTotalPixels = segmentPixels * SEGMENT_COUNT;
      var metresPerSegment = niceMetres / SEGMENT_COUNT;

      barPanel.clear();
      labelPanel.clear();

      for (var i = 0; i < SEGMENT_COUNT; i++) {
        barPanel.add(makeSegment(segmentPixels, i % 2 === 0));
      }

      for (var j = 0; j <= SEGMENT_COUNT; j++) {
        var labelWidth = j === 0 || j === SEGMENT_COUNT ?
          Math.floor(segmentPixels / 2) : segmentPixels;
        var alignment = 'center';
        if (j === 0) alignment = 'left';
        else if (j === SEGMENT_COUNT) alignment = 'right';
        labelPanel.add(makeLabel(
          formatDistance(metresPerSegment * j), labelWidth, alignment
        ));
      }

      barPanel.style().set('width', correctedTotalPixels + 'px');
      labelPanel.style().set('width', correctedTotalPixels + 'px');
    } catch (scaleBarError) {}
  }

  var boundsListenerId = mapWidget.onChangeBounds(function() {
    updateScaleBar();
  });

  updateScaleBar();

  return {
    panel: mainPanel,
    update: function() { updateScaleBar(); },
    remove: function() {
      try {
        mapWidget.unlisten(boundsListenerId);
      } catch (listenerRemovalError) {}
      try {
        mapWidget.remove(mainPanel);
      } catch (panelRemovalError) {}
    }
  };
}

dynamicMapSymbols = addDynamicMapSymbols(map);




var SIMPLE10 = {
  SCALE: 10, EDGE: 1024, MIN_EDGE: 64, BATCH: 40, MAX_GRID: 1000,
  token: 0, busy: false, model: null, modelKey: null, runKey: null,
  plan: null, rootIndex: 0, partIndex: 0, pending: [], active: null,
  ready: 0, batchReady: 0, nextBatch: false, failed: false, finished: false
};
var simple10ModelWidgets = [aoiBox, trainBox, classBox, yearBox, windowBox,
  fallbackBox, targetBox, excludedBox, splitBox, treesBox, bagBox, seedsBox, tileScaleBox];
function simple10ModelKey() {
  return JSON.stringify(simple10ModelWidgets.map(function(widget) {
    return String(widget.getValue()).trim();
  }));
}
function simple10HasMap() {
  return !APP.running && !!APP.finalMap && APP.finalMap === SIMPLE10.model &&
    !!APP.cfg && APP.cfg.scale === 10 && SIMPLE10.modelKey === simple10ModelKey();
}
function simple10Current(token) { return token === SIMPLE10.token && simple10HasMap(); }


var simple10OriginalReadConfig = readConfig;
readConfig = function() {
  var rowText = rowsBox.getValue(), colText = colsBox.getValue(), cfg;
  scaleBox.setValue('10', false);
  rowsBox.setValue('1', false); colsBox.setValue('1', false);
  try { cfg = simple10OriginalReadConfig(); }
  finally { rowsBox.setValue(rowText, false); colsBox.setValue(colText, false); }
  cfg.scale = 10;
  cfg.rows = Number(rowText); cfg.cols = Number(colText);
  return cfg;
};
scaleBox.setValue('10', false);
scaleBox.setDisabled(true);

// Reuse the original rows/columns fields and one original action button.
// Disconnect BOTH legacy download callbacks before hiding the redundant button.
exportButton.unlisten();
tileButton.unlisten();
tileButton.setDisabled(true);
tileButton.style().set('shown', false);
exportButton.setLabel('GENERATE DOWNLOAD LINKS');
for (var simple10UiIndex = 0; simple10UiIndex < control.widgets().length(); simple10UiIndex++) {
  var simple10Widget = control.widgets().get(simple10UiIndex);
  if (simple10Widget === rowsBox || simple10Widget === colsBox) {
    simple10Widget.style().set('shown', true);
    simple10Widget.setDisabled(false);
    if (simple10UiIndex > 0) {
      var simple10Label = control.widgets().get(simple10UiIndex - 1);
      simple10Label.style().set('shown', true);
      simple10Label.setValue(simple10Widget === rowsBox ? 'Number of tile rows' : 'Number of tile columns');
    }
  }
  if (simple10Widget && typeof simple10Widget.getValue === 'function') {
    var simple10Text = simple10Widget.getValue();
    if (typeof simple10Text === 'string' && simple10Text.indexOf('The published App generates direct GeoTIFF') === 0) {
      simple10Widget.setValue('Choose rows and columns, then generate download links. Pixels always stay 10 m. ' +
        'Large cells are divided automatically into labelled parts. Download every part to cover the full cell.');
    }
  }
}

var simple10Host = ui.Panel({style: {stretch: 'horizontal'}});
var simple10Summary = note('Run automated mapping, then generate download links.');
var simple10Progress = ui.Label('', {fontSize: '11px', color: '#0d47a1', whiteSpace: 'pre-wrap'});
var simple10Links = ui.Panel({style: {stretch: 'horizontal'}});
simple10Host.add(simple10Summary);
simple10Host.add(simple10Progress);
simple10Host.add(note('If opening a download link fails, increase rows and columns and generate links again. Pixel size stays 10 m.'));
simple10Host.add(simple10Links);

function simple10Mount() { downloadPanel.clear(); downloadPanel.add(simple10Host); }
function simple10Sync() {
  exportButton.setDisabled(!simple10HasMap());
  exportButton.setLabel(SIMPLE10.busy ? 'PAUSE LINK GENERATION' :
    SIMPLE10.failed ? 'RETRY DOWNLOAD LINKS' :
    SIMPLE10.nextBatch ? 'GENERATE NEXT DOWNLOAD LINKS' :
    SIMPLE10.finished ? 'REGENERATE DOWNLOAD LINKS' :
    SIMPLE10.plan ? 'CONTINUE GENERATING LINKS' : 'GENERATE DOWNLOAD LINKS');
  tileButton.setDisabled(true);
  tileButton.style().set('shown', false);
  [rowsBox, colsBox, prefixBox].forEach(function(widget) { widget.setDisabled(APP.running || SIMPLE10.busy); });
  simple10ModelWidgets.forEach(function(widget) { widget.setDisabled(APP.running); });
  scaleBox.setDisabled(true);
}
function simple10Reset(message) {
  SIMPLE10.token++; APP.downloadGeneration++;
  SIMPLE10.busy = false; SIMPLE10.plan = null;
  SIMPLE10.rootIndex = 0; SIMPLE10.partIndex = 0; SIMPLE10.pending = []; SIMPLE10.active = null;
  SIMPLE10.ready = 0; SIMPLE10.batchReady = 0;
  SIMPLE10.nextBatch = false; SIMPLE10.failed = false; SIMPLE10.finished = false;
  simple10Links.clear(); simple10Progress.setValue('');
  simple10Summary.setValue(message || 'Choose rows and columns, then generate download links.');
  simple10Mount(); simple10Sync();
}
function simple10Service(invoke, callback) {
  var settled = false;
  var timer = ui.util.setTimeout(function() { done(null, 'Preparation timed out.'); }, 120000);
  function done(value, error) {
    if (settled) return;
    settled = true; ui.util.clearTimeout(timer);
    callback(value, error);
  }
  try { invoke(done); } catch (error) { done(null, error); }
}
function simple10GridInput() {
  var rows = Number(rowsBox.getValue()), cols = Number(colsBox.getValue());
  [rows, cols].forEach(function(value) {
    if (!isFinite(value) || Math.floor(value) !== value || value < 1 || value > SIMPLE10.MAX_GRID) {
      throw new Error('Enter whole numbers from 1 to ' + SIMPLE10.MAX_GRID + ' for rows and columns.');
    }
  });
  return {rows: rows, cols: cols};
}
function simple10Utm(lon, lat) {
  if (!isFinite(lon) || !isFinite(lat) || lon < -180 || lon > 180 || lat < -80 || lat > 84) {
    throw new Error('This area needs a different map projection. Contact the app owner.');
  }
  var zone = Math.max(1, Math.min(60, Math.floor((lon + 180) / 6) + 1));
  return 'EPSG:' + ((lat >= 0 ? 32600 : 32700) + zone);
}
function simple10Tile(tile) {
  [tile.x0, tile.yTop, tile.width, tile.height].forEach(function(value) {
    if (!isFinite(value) || Math.floor(value) !== value) throw new Error('Invalid 10 m grid coordinates.');
  });
  if (tile.x0 % 10 || tile.yTop % 10 || tile.width < 1 || tile.height < 1) {
    throw new Error('Invalid 10 m tile dimensions.');
  }
  return tile;
}
function simple10Plan(ring, crs, layout) {
  if (!Array.isArray(ring) || ring.length < 4) throw new Error('The area boundary could not be read.');
  var xs = [], ys = [];
  ring.forEach(function(point) {
    if (!point || !isFinite(point[0]) || !isFinite(point[1])) throw new Error('The area boundary is invalid.');
    xs.push(Number(point[0])); ys.push(Number(point[1]));
  });
  var x0 = Math.floor((Math.min.apply(null, xs) - 1) / 10) * 10;
  var east = Math.ceil((Math.max.apply(null, xs) + 1) / 10) * 10;
  var south = Math.floor((Math.min.apply(null, ys) - 1) / 10) * 10;
  var yTop = Math.ceil((Math.max.apply(null, ys) + 1) / 10) * 10;
  var width = (east - x0) / 10, height = (yTop - south) / 10;
  if (layout.cols > width || layout.rows > height) {
    throw new Error('This area has only ' + height + ' pixel rows and ' + width +
      ' pixel columns at 10 m. Use fewer tile rows or columns.');
  }
  // Counting parts is separable across columns and rows, O(rows + columns).
  // A million requested cells still does not create a million client objects.
  var xParts = 0, yParts = 0;
  for (var c = 0; c < layout.cols; c++) {
    xParts += Math.ceil((Math.floor((c + 1) * width / layout.cols) - Math.floor(c * width / layout.cols)) / SIMPLE10.EDGE);
  }
  for (var r = 0; r < layout.rows; r++) {
    yParts += Math.ceil((Math.floor((r + 1) * height / layout.rows) - Math.floor(r * height / layout.rows)) / SIMPLE10.EDGE);
  }
  return {x0: x0, yTop: yTop, width: width, height: height, rows: layout.rows,
    cols: layout.cols, crs: crs, cells: layout.rows * layout.cols, files: xParts * yParts};
}
function simple10Pad(value) { return ('0000' + value).slice(-4); }
function simple10Root(index) {
  var p = SIMPLE10.plan;
  var r = Math.floor(index / p.cols), c = index % p.cols;
  var x = Math.floor(c * p.width / p.cols), y = Math.floor(r * p.height / p.rows);
  return simple10Tile({row: r + 1, col: c + 1,
    id: 'R' + simple10Pad(r + 1) + '_C' + simple10Pad(c + 1),
    x0: p.x0 + x * 10, yTop: p.yTop - y * 10,
    width: Math.floor((c + 1) * p.width / p.cols) - x,
    height: Math.floor((r + 1) * p.height / p.rows) - y});
}
function simple10Part(root, index) {
  var nx = Math.ceil(root.width / SIMPLE10.EDGE), ny = Math.ceil(root.height / SIMPLE10.EDGE);
  var x = (index % nx) * SIMPLE10.EDGE, y = Math.floor(index / nx) * SIMPLE10.EDGE;
  var multiple = nx * ny > 1;
  return simple10Tile({row: root.row, col: root.col,
    id: root.id + (multiple ? '_part' + (index + 1) : ''),
    label: 'Row ' + root.row + ', column ' + root.col + (multiple ? ' - part ' + (index + 1) : ''),
    x0: root.x0 + x * 10, yTop: root.yTop - y * 10,
    width: Math.min(SIMPLE10.EDGE, root.width - x), height: Math.min(SIMPLE10.EDGE, root.height - y)});
}
function simple10TakeNext() {
  if (SIMPLE10.pending.length) return SIMPLE10.pending.shift();
  if (SIMPLE10.rootIndex >= SIMPLE10.plan.cells) return null;
  var root = simple10Root(SIMPLE10.rootIndex);
  var count = Math.ceil(root.width / SIMPLE10.EDGE) * Math.ceil(root.height / SIMPLE10.EDGE);
  var tile = simple10Part(root, SIMPLE10.partIndex++);
  if (SIMPLE10.partIndex >= count) { SIMPLE10.partIndex = 0; SIMPLE10.rootIndex++; }
  return tile;
}
function simple10CanSplit(tile) {
  return Math.max(tile.width, tile.height) >= SIMPLE10.MIN_EDGE * 2;
}
function simple10Split(tile) {
  simple10Tile(tile);
  if (!simple10CanSplit(tile)) throw new Error('The smallest tile size has been reached.');
  var horizontal = tile.width >= tile.height;
  var half = Math.floor((horizontal ? tile.width : tile.height) / 2);
  return [0, 1].map(function(side) {
    return simple10Tile({row: tile.row, col: tile.col,
      id: tile.id + (side ? '_b' : '_a'), label: tile.label + (side ? ' (b)' : ' (a)'),
      x0: tile.x0 + (horizontal && side ? half * 10 : 0),
      yTop: tile.yTop - (!horizontal && side ? half * 10 : 0),
      width: horizontal ? (side ? tile.width - half : half) : tile.width,
      height: horizontal ? tile.height : (side ? tile.height - half : half)});
  });
}
function simple10Remaining() {
  return !!SIMPLE10.active || SIMPLE10.pending.length > 0 ||
    (SIMPLE10.plan && SIMPLE10.rootIndex < SIMPLE10.plan.cells);
}
function simple10Fatal(error) {
  return /payload|serialized|expression.*large|request.*10.?mb|permission|unauthorized|not authorized|access denied|authentication/i.test(lcErrorText(error));
}
function simple10Error(error) {
  var detail = lcErrorText(error);
  if (/payload|serialized|expression.*large|request.*10.?mb/i.test(detail)) {
    return 'This map is too complex for an immediate download. The app owner needs to prepare it for downloading at 10 m.';
  }
  if (/permission|unauthorized|not authorized|access denied|authentication/i.test(detail)) {
    return 'The map could not be accessed. Reload the app or contact the app owner.';
  }
  return 'This link could not be prepared. Click RETRY DOWNLOAD LINKS. If it keeps failing, increase rows and columns.';
}
function simple10StopWithError(token, error, planning) {
  if (!simple10Current(token)) return;
  SIMPLE10.busy = false; SIMPLE10.failed = true;
  simple10Progress.style().set('color', '#b71c1c');
  simple10Progress.setValue(planning ? lcErrorText(error) : simple10Error(error));
  if (SIMPLE10.active) SIMPLE10.active.widget.setValue(SIMPLE10.active.tile.label + ' - link failed; awaiting retry.');
  print('10 m download:', lcErrorText(error));
  simple10Sync();
}
function simple10SummaryText() {
  var p = SIMPLE10.plan;
  return p.rows + ' rows x ' + p.cols + ' columns; ' + p.files + ' download files at 10 m.' +
    (p.files > p.cells ? ' Large cells include smaller parts.' : '') +
    ' The grid covers the area extent; outside/missing pixels are 0, classes are 1-12.';
}
function simple10Build() {
  var layout;
  try { layout = simple10GridInput(); }
  catch (inputError) { simple10Progress.setValue(lcErrorText(inputError)); return; }
  simple10Reset('Preparing your ' + layout.rows + ' x ' + layout.cols + ' grid at 10 m...');
  SIMPLE10.busy = true;
  var token = ++SIMPLE10.token;
  simple10Sync();
  simple10Service(function(done) {
    APP.roi.geometry().centroid(1, ee.Projection('EPSG:4326')).coordinates().evaluate(done);
  }, function(coords, error) {
    if (!simple10Current(token)) return;
    if (error || !coords || coords.length < 2) { simple10StopWithError(token, error || 'The area centre could not be read.', true); return; }
    var crs;
    try { crs = simple10Utm(Number(coords[0]), Number(coords[1])); }
    catch (projectionError) { simple10StopWithError(token, projectionError, true); return; }
    simple10Service(function(done) {
      APP.roi.geometry().bounds(1, ee.Projection(crs)).coordinates().evaluate(done);
    }, function(polygons, boundsError) {
      if (!simple10Current(token)) return;
      if (boundsError) { simple10StopWithError(token, boundsError, true); return; }
      try {
        SIMPLE10.plan = simple10Plan(polygons && polygons[0], crs, layout);
        simple10Summary.setValue(simple10SummaryText());
        simple10Next(token);
      } catch (gridError) { simple10StopWithError(token, gridError, true); }
    });
  });
}
function simple10Next(token) {
  if (!simple10Current(token) || !SIMPLE10.busy) return;
  if (!simple10Remaining()) {
    SIMPLE10.busy = false; SIMPLE10.finished = true;
    simple10Progress.setValue('All ' + SIMPLE10.ready + ' links have been prepared. Download the files shown below. ' +
      'The same button can regenerate links from the beginning.');
    simple10Sync(); return;
  }
  if (SIMPLE10.batchReady >= SIMPLE10.BATCH) {
    SIMPLE10.busy = false; SIMPLE10.nextBatch = true;
    simple10Progress.setValue(SIMPLE10.ready + ' of ' + SIMPLE10.plan.files + ' links prepared. ' +
      'Download these ' + SIMPLE10.batchReady + ' files, then use the same button for the next links. ' +
      'The current list will be replaced.');
    simple10Sync(); return;
  }
  if (!SIMPLE10.active) {
    var tile = simple10TakeNext();
    var widget = ui.Label(tile.label + ' - preparing...', {fontSize: '11px', whiteSpace: 'pre-wrap'});
    SIMPLE10.active = {tile: tile, widget: widget, tries: 0};
    simple10Links.add(widget);
  }
  var active = SIMPLE10.active;
  active.tries++;
  active.widget.setValue(active.tile.label + ' - preparing...');
  simple10Progress.style().set('color', '#0d47a1');
  simple10Progress.setValue('Preparing link ' + (SIMPLE10.ready + 1) + ' of ' + SIMPLE10.plan.files +
    '. Click a ready link below to download. Pixel size: 10 m.');
  simple10Service(function(done) {
    var tile = simple10Tile(active.tile);
    if (tile.width > SIMPLE10.EDGE || tile.height > SIMPLE10.EDGE) throw new Error('Download part exceeds the size limit.');
    var name = (clean(prefixBox.getValue()) || 'landcover') + '_' + APP.cfg.targetYear +
      '_seed' + APP.best.seed + '_' + SIMPLE10.plan.rows + 'x' + SIMPLE10.plan.cols + '_' + tile.id + '_10m';
    ee.Image(APP.finalMap).rename('classification').toUint8().clip(APP.roi.geometry()).unmask(0, false)
      .getDownloadURL({name: name, crs: SIMPLE10.plan.crs,
        crs_transform: [10, 0, tile.x0, 0, -10, tile.yTop], dimensions: [tile.width, tile.height],
        filePerBand: false, format: 'ZIPPED_GEO_TIFF'}, done);
  }, function(url, error) {
    if (!simple10Current(token) || !SIMPLE10.busy) return;
    if (!error && typeof url === 'string' && /^https:\/\//.test(url)) {
      active.widget.setValue(active.tile.label + ' - Download GeoTIFF (ZIP)');
      active.widget.setUrl(url);
      active.widget.style().set({color: '#0b57d0', textDecoration: 'underline'});
      SIMPLE10.active = null; SIMPLE10.ready++; SIMPLE10.batchReady++;
    } else {
      error = error || 'No valid download link was returned.';
      print(active.tile.id + ':', lcErrorText(error));
      if (simple10Fatal(error)) { simple10StopWithError(token, error, false); return; }
      if (/memory|timed out|timeout|size|pixels|dimensions/i.test(lcErrorText(error)) && simple10CanSplit(active.tile)) {
        var parts = simple10Split(active.tile);
        SIMPLE10.pending = parts.concat(SIMPLE10.pending);
        SIMPLE10.plan.files += parts.length - 1;
        simple10Links.remove(active.widget); SIMPLE10.active = null;
        simple10Summary.setValue(simple10SummaryText());
      } else if (active.tries >= 2) { simple10StopWithError(token, error, false); return; }
    }
    // Yield between requests so the single pause button stays responsive.
    ui.util.setTimeout(function() { simple10Next(token); }, 100);
  });
}
function simple10Click() {
  if (!simple10HasMap()) return;
  if (SIMPLE10.busy) {
    SIMPLE10.token++; SIMPLE10.busy = false;
    if (SIMPLE10.active) SIMPLE10.active.widget.setValue(SIMPLE10.active.tile.label + ' - paused.');
    simple10Progress.setValue('Paused. Ready links remain available. Use the same button to continue.');
    simple10Sync(); return;
  }
  if (!SIMPLE10.plan || SIMPLE10.finished) { simple10Build(); return; }
  if (SIMPLE10.nextBatch) {
    simple10Links.clear(); SIMPLE10.batchReady = 0; SIMPLE10.nextBatch = false;
  }
  SIMPLE10.failed = false;
  if (SIMPLE10.active) SIMPLE10.active.tries = 0;
  SIMPLE10.busy = true;
  var token = ++SIMPLE10.token;
  simple10Sync(); simple10Next(token);
}
exportButton.onClick(simple10Click);

[rowsBox, colsBox, prefixBox].forEach(function(widget) {
  widget.onChange(function() {
    simple10Reset(simple10HasMap() ? 'Download settings changed. Generate new links for this grid.' :
      'Run automated mapping, then generate download links.');
  });
});
function simple10Invalidate() {
  SIMPLE10.model = null; SIMPLE10.modelKey = null; APP.finalMap = null;
  simple10Reset('Model settings changed. Run automated mapping again before downloading.');
  if (!APP.running) setStatus('Settings changed. Run automated mapping again.', '#e65100');
}
simple10ModelWidgets.forEach(function(widget) { widget.onChange(simple10Invalidate); });

var simple10OriginalFinish = finish;
finish = function(best, cfg, roi) {
  if (cfg.scale !== 10 || SIMPLE10.runKey !== simple10ModelKey()) {
    APP.running = false; runButton.setDisabled(false);
    simple10Invalidate();
    setStatus('Settings changed during mapping. Run automated mapping again.', '#b71c1c');
    return;
  }
  simple10OriginalFinish(best, cfg, roi);
  SIMPLE10.model = APP.finalMap; SIMPLE10.modelKey = simple10ModelKey();
  simple10Reset('Map ready. Choose rows and columns, then generate download links at 10 m.');
  setStatus('Complete. Best seed ' + best.seed + '. Review the results, then generate download links.', '#1b5e20');
};
var simple10OriginalRun = run;
run = function() {
  if (APP.running) return;
  SIMPLE10.model = null; SIMPLE10.modelKey = null; APP.finalMap = null;
  SIMPLE10.runKey = simple10ModelKey();
  simple10Reset('Running automated mapping. Download pixels will remain 10 m.');
  try { simple10OriginalRun(); }
  catch (error) {
    APP.running = false; runButton.setDisabled(false);
    setStatus('Mapping error: ' + lcErrorText(error), '#b71c1c');
  }
  simple10Mount(); simple10Sync();
};
runButton.unlisten();
runButton.onClick(run);
var simple10OriginalSetStatus = setStatus;
setStatus = function(message, color) { simple10OriginalSetStatus(message, color); simple10Sync(); };
simple10Reset('Run automated mapping, choose rows and columns, then generate download links.');




var LC10_CACHE = {
  assetId: '',
  prepareInCodeEditor: false
};
var CACHE10 = {generation: 0, loadedAsset: null, grid: null, preparing: false,
  operation: null, MAX_SIDE: 8192, MAX_PIXELS: 24 * 1024 * 1024};

// Retain the source of the legacy conversion above, but never execute it.
materializeBestModel = function(best, cfg, roi, embeddings, terrain) {
  if (!best || !best.map || !best.yearly) {
    APP.running = false; runButton.setDisabled(false);
    setStatus('The selected model did not return its final and yearly maps.', '#b71c1c');
    return;
  }
  setStatus('Preparing the selected map at 10 m...', '#0d47a1');
  finish(best, cfg, roi);
};

function cache10ConfigKey(cfg) {
  return JSON.stringify([cfg.aoi, cfg.training, cfg.classField, cfg.targetYear,
    cfg.years, cfg.fallback, cfg.targetAccuracy, cfg.excluded, cfg.trainFraction,
    cfg.trees, cfg.bag, cfg.seeds, cfg.scale, cfg.tileScale]);
}
function cache10ValidRun(generation, key) {
  return generation === CACHE10.generation && key === simple10ModelKey();
}
function cache10AssetId() { return String(LC10_CACHE.assetId || '').trim(); }
function cache10Metadata(image, done) {
  var projection = image.select('classification').projection();
  ee.Dictionary({
    properties: image.toDictionary(['lc10_schema', 'lc10_config', 'lc10_metrics', 'lc10_grid']),
    bands: image.bandNames(), crs: projection.crs(), transform: projection.transform()
  }).evaluate(done);
}
function cache10Validate(data, cfg) {
  if (!data || !data.properties || data.properties.lc10_schema !== 1) throw new Error('Prepared-map metadata is missing.');
  var p = data.properties;
  if (p.lc10_config !== cache10ConfigKey(cfg)) throw new Error('The prepared map belongs to different model settings.');
  var grid = JSON.parse(p.lc10_grid), metrics = JSON.parse(p.lc10_metrics);
  var transform = data.transform;
  if (!/^EPSG:32[67]\d\d$/.test(data.crs) || data.crs !== grid.crs || !Array.isArray(transform) ||
      transform.length !== 6 || transform[0] !== 10 || transform[1] !== 0 ||
      transform[3] !== 0 || transform[4] !== -10 ||
      transform[2] !== grid.x0 || transform[5] !== grid.yTop) {
    throw new Error('The prepared raster does not have the required aligned 10 m UTM grid.');
  }
  simple10Tile({x0: grid.x0, yTop: grid.yTop, width: grid.width, height: grid.height});
  var required = ['classification'].concat(cfg.years.map(function(year) { return 'c' + year; }));
  required.forEach(function(band) {
    if (!Array.isArray(data.bands) || data.bands.indexOf(band) < 0) throw new Error('Prepared map is missing band ' + band + '.');
  });
  ['seed', 'score', 'overall', 'kappa'].forEach(function(name) {
    if (typeof metrics[name] !== 'number' || !isFinite(metrics[name])) throw new Error('Prepared-map accuracy metadata is incomplete.');
  });
  if (!Array.isArray(metrics.prod) || metrics.prod.length !== classValues.length ||
      !Array.isArray(metrics.conf) || metrics.conf.length !== classValues.length ||
      metrics.conf.some(function(row) { return !Array.isArray(row) || row.length !== classValues.length; })) {
    throw new Error('Prepared-map accuracy tables are incomplete.');
  }
  return {grid: grid, metrics: metrics};
}
function cache10Use(image, data, cfg, roi, assetId) {
  var verified = cache10Validate(data, cfg), best = verified.metrics;
  best.map = image.select('classification'); best.yearly = {}; best.classifiers = null;
  cfg.years.forEach(function(year) { best.yearly[year] = image.select('c' + year); });
  CACHE10.loadedAsset = assetId; CACHE10.grid = verified.grid;
  SIMPLE10.runKey = simple10ModelKey();
  finish(best, cfg, roi);
  setStatus('Complete. Loaded the prepared 10 m map. Choose rows and columns, then generate links.', '#1b5e20');
}
function cache10Read(assetId, cfg, done) {
  simple10Service(function(callback) { cache10Metadata(ee.Image(assetId), callback); }, function(data, error) {
    if (error) { done(null, error); return; }
    try { cache10Validate(data, cfg); }
    catch (validationError) { done(null, validationError); return; }
    done(data, null);
  });
}

function cache10Prepare(best, cfg, roi) {
  if (!LC10_CACHE.prepareInCodeEditor || CACHE10.preparing || CACHE10.loadedAsset) return;
  var assetId = cache10AssetId();
  if (!/^projects\/[^/]+\/assets\/.+/.test(assetId)) {
    setStatus('Owner setup: enter a new projects/.../assets/... image path in LC10_CACHE.assetId.', '#b71c1c');
    return;
  }
  if (!ee.data || typeof ee.data.startProcessing !== 'function') {
    setStatus('Owner preparation must run in an authenticated Earth Engine Code Editor.', '#b71c1c');
    return;
  }
  var generation = CACHE10.generation, key = simple10ModelKey();
  CACHE10.preparing = true; CACHE10.operation = null;
  simple10Sync();
  setStatus('Owner preparation: checking the new asset destination...', '#0d47a1');
  function fail(error) {
    if (!cache10ValidRun(generation, key)) return;
    CACHE10.preparing = false;
    setStatus('Owner preparation: ' + lcErrorText(error), '#b71c1c');
    print('Prepared-map export:', lcErrorText(error));
  }
  simple10Service(function(done) { ee.data.getAsset(assetId, done); }, function(existing, assetError) {
    if (!cache10ValidRun(generation, key)) return;
    if (existing) { fail('That asset already exists. Use a new asset ID; existing data will not be overwritten.'); return; }
    if (!assetError || !/not found|does not exist|404/i.test(lcErrorText(assetError))) {
      fail(assetError || 'The destination could not be verified.'); return;
    }
    simple10Service(function(done) {
      roi.geometry().centroid(1, ee.Projection('EPSG:4326')).coordinates().evaluate(done);
    }, function(coords, centreError) {
      if (!cache10ValidRun(generation, key)) return;
      if (centreError || !coords || coords.length < 2) { fail(centreError || 'The area centre could not be read.'); return; }
      var crs;
      try { crs = simple10Utm(Number(coords[0]), Number(coords[1])); }
      catch (projectionError) { fail(projectionError); return; }
      simple10Service(function(done) {
        roi.geometry().bounds(1, ee.Projection(crs)).coordinates().evaluate(done);
      }, function(polygons, boundsError) {
        if (!cache10ValidRun(generation, key)) return;
        if (boundsError) { fail(boundsError); return; }
        try {
          var p = cache10OriginalPlan(polygons && polygons[0], crs, {rows: 1, cols: 1});
          var grid = {crs: p.crs, x0: p.x0, yTop: p.yTop, width: p.width, height: p.height};
          var metrics = {seed: best.seed, score: best.score, overall: best.overall,
            kappa: best.kappa, prod: best.prod, conf: best.conf};
          var bands = [ee.Image(best.map).rename('classification')];
          cfg.years.forEach(function(year) { bands.push(ee.Image(best.yearly[year]).rename('c' + year)); });
          var stack = ee.Image.cat(bands).toUint8().set({
            lc10_schema: 1, lc10_config: cache10ConfigKey(cfg),
            lc10_metrics: JSON.stringify(metrics), lc10_grid: JSON.stringify(grid)
          });
          var region = ee.Geometry.Rectangle([p.x0, p.yTop - p.height * 10,
            p.x0 + p.width * 10, p.yTop], ee.Projection(crs), false);
          var task = {type: 'EXPORT_IMAGE', element: stack, assetId: assetId,
            description: clean('prepare_lc10_' + cfg.targetYear + '_seed' + best.seed),
            crs: crs, crs_transform: [10, 0, p.x0, 0, -10, p.yTop], region: region,
            maxPixels: 1e13, shardSize: 128, pyramidingPolicy: {'.default': 'MODE'}, overwrite: false};
          setStatus('Owner preparation: starting the 10 m batch export...', '#0d47a1');
          ee.data.startProcessing(null, task, function(response, startError) {
            if (!cache10ValidRun(generation, key)) return;
            if (startError || !response || !response.name) {
              fail(startError || 'No operation name was returned. Check your EE operations before starting another export.'); return;
            }
            CACHE10.operation = response.name;
            print('10 m prepared-map operation:', response.name);
            print('Destination (available only after successful completion):', assetId);
            cache10Watch(response.name, generation, key, assetId, cfg, roi, 0);
          });
        } catch (exportError) { fail(exportError); }
      });
    });
  });
}
function cache10Watch(operation, generation, key, assetId, cfg, roi, failures) {
  if (!cache10ValidRun(generation, key)) return;
  simple10Service(function(done) { ee.data.getOperation(operation, done); }, function(result, error) {
    if (!cache10ValidRun(generation, key)) return;
    if (error || !result) {
      if (failures < 3) {
        ui.util.setTimeout(function() { cache10Watch(operation, generation, key, assetId, cfg, roi, failures + 1); }, 15000);
      } else {
        CACHE10.preparing = false;
        setStatus('Could not refresh preparation progress. The batch may still be running; do not start another export. ' +
          'Operation: ' + operation, '#b71c1c');
      }
      return;
    }
    var state = result.metadata && result.metadata.state;
    if (result.error || state === 'FAILED' || state === 'CANCELLED') {
      CACHE10.preparing = false;
      setStatus('10 m preparation failed: ' + lcErrorText(result.error || state), '#b71c1c');
      return;
    }
    if (result.done && state === 'SUCCEEDED') {
      cache10Read(assetId, cfg, function(data, loadError) {
        if (!cache10ValidRun(generation, key)) return;
        CACHE10.preparing = false;
        if (loadError) { setStatus('The export finished, but its asset could not be loaded: ' + lcErrorText(loadError), '#b71c1c'); return; }
        try { cache10Use(ee.Image(assetId), data, cfg, roi, assetId); }
        catch (useError) { setStatus('Prepared-map validation failed: ' + lcErrorText(useError), '#b71c1c'); return; }
        setStatus('10 m map saved and ready. Owner: share this image with the App and set prepareInCodeEditor to false before publishing.', '#1b5e20');
      });
      return;
    }
    setStatus('Preparing the saved 10 m map: ' + (state || 'PENDING') +
      '. This may take time; the batch is already running. No Tasks-tab action is needed.', '#0d47a1');
    ui.util.setTimeout(function() { cache10Watch(operation, generation, key, assetId, cfg, roi, 0); }, 15000);
  });
}

var cache10LiveRun = run;
run = function() {
  if (APP.running || CACHE10.preparing) return;
  var cfg;
  try { cfg = readConfig(); }
  catch (error) { setStatus('Input error: ' + lcErrorText(error), '#b71c1c'); return; }
  var generation = ++CACHE10.generation, key = simple10ModelKey();
  CACHE10.loadedAsset = null; CACHE10.grid = null; CACHE10.operation = null;
  var assetId = cache10AssetId();
  if (!assetId) { cache10LiveRun(); return; }
  APP.finalMap = null; SIMPLE10.model = null; SIMPLE10.modelKey = null;
  SIMPLE10.runKey = key; APP.running = true; runButton.setDisabled(true);
  simple10Reset('Checking the prepared 10 m map...');
  setStatus('Loading the prepared map...', '#0d47a1');
  cache10Read(assetId, cfg, function(data, error) {
    if (!cache10ValidRun(generation, key)) {
      APP.running = false; runButton.setDisabled(false);
      setStatus('Settings changed while loading. Run automated mapping again.', '#e65100'); return;
    }
    if (error) {
      print('Prepared map unavailable or settings differ; using the original live model:', lcErrorText(error));
      APP.running = false; runButton.setDisabled(false);
      cache10LiveRun(); return;
    }
    try { cache10Use(ee.Image(assetId), data, cfg, ee.FeatureCollection(cfg.aoi), assetId); }
    catch (useError) {
      APP.running = false; runButton.setDisabled(false);
      CACHE10.loadedAsset = null; CACHE10.grid = null;
      setStatus('Prepared-map error: ' + lcErrorText(useError), '#b71c1c');
    }
  });
};
runButton.unlisten(); runButton.onClick(run);

var cache10Finish = finish;
finish = function(best, cfg, roi) {
  cache10Finish(best, cfg, roi);
  if (simple10HasMap() && !CACHE10.loadedAsset) cache10Prepare(best, cfg, roi);
};
var cache10Sync = simple10Sync;
simple10Sync = function() {
  cache10Sync();
  if (CACHE10.preparing) {
    exportButton.setDisabled(true); runButton.setDisabled(true);
    simple10ModelWidgets.concat([rowsBox, colsBox, prefixBox]).forEach(function(widget) { widget.setDisabled(true); });
  } else if (!APP.running) { runButton.setDisabled(false); }
};

function cache10Shape(width, height, prepared) {
  var stepX = prepared ? Math.min(width, CACHE10.MAX_SIDE) : Math.min(width, SIMPLE10.EDGE);
  var stepY = prepared ? Math.min(height, CACHE10.MAX_SIDE, Math.floor(CACHE10.MAX_PIXELS / stepX)) : Math.min(height, SIMPLE10.EDGE);
  return {x: stepX, y: stepY, nx: Math.ceil(width / stepX), ny: Math.ceil(height / stepY)};
}
var cache10OriginalPlan = simple10Plan;
simple10Plan = function(ring, crs, layout) {
  var p = cache10OriginalPlan(ring, crs, layout);
  p.prepared = !!CACHE10.loadedAsset;
  if (!p.prepared) return p;
  p.x0 = CACHE10.grid.x0; p.yTop = CACHE10.grid.yTop;
  p.width = CACHE10.grid.width; p.height = CACHE10.grid.height; p.crs = CACHE10.grid.crs;
  if (layout.cols > p.width || layout.rows > p.height) throw new Error('Use fewer rows or columns for this 10 m raster.');
  var smallW = Math.floor(p.width / p.cols), extraW = p.width % p.cols;
  var smallH = Math.floor(p.height / p.rows), extraH = p.height % p.rows;
  p.files = 0;
  [[smallW, p.cols - extraW], [smallW + 1, extraW]].forEach(function(w) {
    [[smallH, p.rows - extraH], [smallH + 1, extraH]].forEach(function(h) {
      var shape = cache10Shape(w[0], h[0], true);
      p.files += w[1] * h[1] * shape.nx * shape.ny;
    });
  });
  return p;
};
simple10Part = function(root, index) {
  var shape = cache10Shape(root.width, root.height, SIMPLE10.plan.prepared);
  var x = (index % shape.nx) * shape.x, y = Math.floor(index / shape.nx) * shape.y;
  var multiple = shape.nx * shape.ny > 1;
  return simple10Tile({row: root.row, col: root.col,
    id: root.id + (multiple ? '_part' + (index + 1) : ''),
    label: 'Row ' + root.row + ', column ' + root.col + (multiple ? ' - part ' + (index + 1) : ''),
    x0: root.x0 + x * 10, yTop: root.yTop - y * 10,
    width: Math.min(shape.x, root.width - x), height: Math.min(shape.y, root.height - y)});
};
simple10TakeNext = function() {
  if (SIMPLE10.pending.length) return SIMPLE10.pending.shift();
  if (SIMPLE10.rootIndex >= SIMPLE10.plan.cells) return null;
  var root = simple10Root(SIMPLE10.rootIndex);
  var shape = cache10Shape(root.width, root.height, SIMPLE10.plan.prepared);
  var tile = simple10Part(root, SIMPLE10.partIndex++);
  if (SIMPLE10.partIndex >= shape.nx * shape.ny) { SIMPLE10.partIndex = 0; SIMPLE10.rootIndex++; }
  return tile;
};


var cache10Next = simple10Next;
simple10Next = function(token) {
  var oldEdge = SIMPLE10.EDGE;
  if (SIMPLE10.plan && SIMPLE10.plan.prepared) SIMPLE10.EDGE = CACHE10.MAX_SIDE;
  try {
    var active = SIMPLE10.active;
    if (active && SIMPLE10.plan && SIMPLE10.plan.prepared &&
        active.tile.width * active.tile.height > CACHE10.MAX_PIXELS) {
      simple10StopWithError(token, 'The prepared-map file exceeded the pixel budget.', false); return;
    }
    cache10Next(token);
  } finally { SIMPLE10.EDGE = oldEdge; }
};
var cache10Summary = simple10SummaryText;
simple10SummaryText = function() {
  return cache10Summary() + (SIMPLE10.plan.prepared ? ' Using the prepared 10 m image.' : ' Using the selected server-side model.');
};
simple10Error = function(error) {
  var detail = lcErrorText(error);
  if (/payload|serialized|expression.*large|request.*10.?mb/i.test(detail)) {
    return 'The request still exceeds the model-size limit. More rows cannot fix this error. ' +
      'Use the owner prepared-map setup in this file. Details: ' + detail.slice(0, 300);
  }
  if (/permission|unauthorized|not authorized|access denied|authentication/i.test(detail)) {
    return 'The map could not be accessed. The owner must share the required assets with this App.';
  }
  return 'This link could not be prepared. Retry with the same button. If live-model requests keep failing, ' +
    'the owner can prepare the 10 m map using the setup in this file. Details: ' + detail.slice(0, 200);
};
for (var cache10HintIndex = 0; cache10HintIndex < simple10Host.widgets().length(); cache10HintIndex++) {
  var cache10Hint = simple10Host.widgets().get(cache10HintIndex);
  if (cache10Hint && typeof cache10Hint.getValue === 'function' &&
      String(cache10Hint.getValue()).indexOf('If opening a download link fails, increase rows') === 0) {
    cache10Hint.setValue('Pixels stay 10 m. If a file fails after opening its link, a prepared 10 m map may be needed; ask the app owner.');
  }
}
simple10Sync();

exportButton.unlisten();
exportButton.onClick(simple10Click);
tileButton.unlisten();
tileButton.setDisabled(true);
tileButton.style().set('shown', false);

function direct10FinalSync() {
  var modelReady = simple10HasMap();
  var blocked = APP.running || CACHE10.preparing;
  exportButton.setDisabled(blocked || !modelReady);
  exportButton.setLabel(
    SIMPLE10.busy ? 'PAUSE LINK GENERATION' :
    SIMPLE10.failed ? 'RETRY DOWNLOAD LINKS' :
    SIMPLE10.nextBatch ? 'GENERATE NEXT DOWNLOAD LINKS' :
    SIMPLE10.finished ? 'REGENERATE DOWNLOAD LINKS' :
    SIMPLE10.plan ? 'CONTINUE GENERATING LINKS' :
    'GENERATE DOWNLOAD LINKS'
  );
  tileButton.setDisabled(true);
  tileButton.style().set('shown', false);
  [rowsBox, colsBox, prefixBox].forEach(function(widget) {
    widget.setDisabled(blocked || SIMPLE10.busy);
  });
  simple10ModelWidgets.forEach(function(widget) {
    widget.setDisabled(blocked);
  });
  scaleBox.setValue('10', false);
  scaleBox.setDisabled(true);
  runButton.setDisabled(blocked);
}
simple10Sync = direct10FinalSync;

for (var direct10UiIndex = 0;
     direct10UiIndex < control.widgets().length();
     direct10UiIndex++) {
  var direct10Widget = control.widgets().get(direct10UiIndex);
  if (direct10Widget && typeof direct10Widget.getValue === 'function') {
    var direct10Text = String(direct10Widget.getValue());
    if (direct10Text.indexOf('Choose rows and columns.') === 0 ||
        direct10Text.indexOf('The published App generates direct GeoTIFF') === 0) {
      direct10Widget.setValue(
        'Choose rows and columns, then generate the direct download links. ' +
        'Pixels always stay 10 m. Large cells are divided automatically into ' +
        'labelled parts when required. Download every ready part to cover the ' +
        'complete map.'
      );
    }
  }
}

// Cancel callbacks from any earlier download attempt and initialize cleanly.
SIMPLE10.token++;
APP.downloadGeneration++;
SIMPLE10.busy = false;
SIMPLE10.pending = [];
SIMPLE10.active = null;
simple10Reset(
  simple10HasMap() ?
    'Map ready. Choose rows and columns, then generate direct 10 m download links.' :
    'Run automated mapping, choose rows and columns, then generate direct 10 m download links.'
);
simple10Sync();


var EXACT10_MAX_SIDE = 10000;
var EXACT10_MAX_BYTES = 32 * 1024 * 1024;
var EXACT10_BYTES_PER_PIXEL = 1;

var exact10BasePlan = simple10Plan;
simple10Plan = function(ring, crs, layout) {
  var p = exact10BasePlan(ring, crs, layout);
  p.files = p.cells;
  p.prepared = !!CACHE10.loadedAsset;

  var maxCellWidth = Math.ceil(p.width / p.cols);
  var maxCellHeight = Math.ceil(p.height / p.rows);
  var maxCellBytes = maxCellWidth * maxCellHeight * EXACT10_BYTES_PER_PIXEL;

  if (maxCellWidth > EXACT10_MAX_SIDE ||
      maxCellHeight > EXACT10_MAX_SIDE ||
      maxCellBytes > EXACT10_MAX_BYTES) {
    var minColsBySide = Math.ceil(p.width / EXACT10_MAX_SIDE);
    var minRowsBySide = Math.ceil(p.height / EXACT10_MAX_SIDE);
    var maxPixels = Math.floor(EXACT10_MAX_BYTES / EXACT10_BYTES_PER_PIXEL);
    var minColsByBytes = Math.ceil(p.width / Math.max(1, Math.floor(maxPixels / Math.ceil(p.height / layout.rows))));
    var minRowsByBytes = Math.ceil(p.height / Math.max(1, Math.floor(maxPixels / Math.ceil(p.width / layout.cols))));
    var suggestedCols = Math.max(layout.cols, minColsBySide, minColsByBytes);
    var suggestedRows = Math.max(layout.rows, minRowsBySide, minRowsByBytes);

    throw new Error(
      layout.rows + ' rows x ' + layout.cols + ' columns would correctly mean exactly ' +
      (layout.rows * layout.cols) + ' files, but each 10 m file would exceed the direct ' +
      'Earth Engine download limit. No hidden subdivision was created. Use at least ' +
      suggestedRows + ' rows x ' + suggestedCols + ' columns for direct downloads, or ' +
      'use an owner-managed batch/cloud service to retain exactly ' +
      (layout.rows * layout.cols) + ' large files.'
    );
  }
  return p;
};

simple10Part = function(root, index) {
  if (index !== 0) throw new Error('Internal exact-grid error: one file is allowed per requested cell.');
  return simple10Tile({
    row: root.row,
    col: root.col,
    id: root.id,
    label: 'Row ' + root.row + ', column ' + root.col,
    x0: root.x0,
    yTop: root.yTop,
    width: root.width,
    height: root.height
  });
};

simple10TakeNext = function() {
  if (SIMPLE10.pending.length) {
    throw new Error('Internal exact-grid error: automatic subdivision is disabled.');
  }
  if (SIMPLE10.rootIndex >= SIMPLE10.plan.cells) return null;
  var root = simple10Root(SIMPLE10.rootIndex++);
  return simple10Part(root, 0);
};

simple10CanSplit = function() { return false; };
simple10Split = function() {
  throw new Error('Automatic subdivision is disabled because rows x columns must equal the exact number of files.');
};

simple10SummaryText = function() {
  var p = SIMPLE10.plan;
  return p.rows + ' rows x ' + p.cols + ' columns = exactly ' + p.cells +
    ' download files at 10 m. No hidden parts. Outside/missing pixels are 0; classes are 1-12.';
};

SIMPLE10.BATCH = SIMPLE10.MAX_GRID * SIMPLE10.MAX_GRID;

for (var exactCountUiIndex = 0;
     exactCountUiIndex < control.widgets().length();
     exactCountUiIndex++) {
  var exactCountWidget = control.widgets().get(exactCountUiIndex);
  if (exactCountWidget && typeof exactCountWidget.getValue === 'function') {
    var exactCountText = String(exactCountWidget.getValue());
    if (exactCountText.indexOf('Choose rows and columns') === 0) {
      exactCountWidget.setValue(
        'Rows x columns is the exact number of download files. For example, ' +
        '2 rows x 5 columns produces exactly 10 files. Pixels stay 10 m. ' +
        'The App does not create hidden parts.'
      );
    }
  }
}

SIMPLE10.token++;
APP.downloadGeneration++;
SIMPLE10.busy = false;
SIMPLE10.plan = null;
SIMPLE10.pending = [];
SIMPLE10.active = null;
simple10Reset(
  simple10HasMap() ?
    'Map ready. Rows x columns will equal the exact number of 10 m files.' :
    'Run automated mapping. Rows x columns will equal the exact number of 10 m files.'
);
simple10Sync();


var EXACT_DRIVE_FOLDER = 'FAO_LandCover_Exports';
var EXACT_EXPORT = {busy: false, generation: 0};

function exactExportLayout() {
  var layout = simple10GridInput();
  layout.count = layout.rows * layout.cols;
  if (layout.count > 1000) {
    throw new Error('Use a maximum of 1000 export tiles.');
  }
  return layout;
}

function exactExportPlan(ring, crs, layout) {
  // Use the original grid planner only for its aligned 10 m extent. Its former
  // immediate-download part count is deliberately ignored.
  var p = cache10OriginalPlan(ring, crs, layout);
  p.cells = layout.rows * layout.cols;
  p.files = p.cells;
  p.rows = layout.rows;
  p.cols = layout.cols;
  return p;
}

function exactExportRoot(p, index) {
  var row = Math.floor(index / p.cols);
  var col = index % p.cols;
  var x1 = Math.floor(col * p.width / p.cols);
  var x2 = Math.floor((col + 1) * p.width / p.cols);
  var y1 = Math.floor(row * p.height / p.rows);
  var y2 = Math.floor((row + 1) * p.height / p.rows);
  return {
    row: row + 1,
    col: col + 1,
    x0: p.x0 + x1 * 10,
    yTop: p.yTop - y1 * 10,
    width: x2 - x1,
    height: y2 - y1
  };
}

function exactExportPad(value) {
  return ('0000' + value).slice(-4);
}

function exactExportSetUi() {
  var blocked = APP.running || CACHE10.preparing || EXACT_EXPORT.busy;
  exportButton.setDisabled(blocked || !simple10HasMap());
  exportButton.setLabel(EXACT_EXPORT.busy ?
    'CREATING EXPORT TASKS...' : 'EXPORT EXACT TILES TO GOOGLE DRIVE');
  tileButton.setDisabled(true);
  tileButton.style().set('shown', false);
  [rowsBox, colsBox, prefixBox].forEach(function(widget) {
    widget.setDisabled(blocked);
  });
  simple10ModelWidgets.forEach(function(widget) {
    widget.setDisabled(APP.running || CACHE10.preparing);
  });
  scaleBox.setValue('10', false);
  scaleBox.setDisabled(true);
  runButton.setDisabled(APP.running || CACHE10.preparing || EXACT_EXPORT.busy);
}

function exactExportToDrive() {
  if (!simple10HasMap() || EXACT_EXPORT.busy) return;
  var layout;
  try {
    layout = exactExportLayout();
  } catch (inputError) {
    simple10Progress.setValue(lcErrorText(inputError));
    setStatus(lcErrorText(inputError), '#b71c1c');
    return;
  }
  if (typeof Export === 'undefined' || !Export.image ||
      typeof Export.image.toDrive !== 'function') {
    simple10Progress.setValue(
      'Batch export is unavailable in this execution environment. Open this complete script in the authenticated Earth Engine Code Editor.'
    );
    setStatus('Google Drive batch export is unavailable here.', '#b71c1c');
    return;
  }

  EXACT_EXPORT.busy = true;
  var generation = ++EXACT_EXPORT.generation;
  simple10Links.clear();
  simple10Summary.setValue(
    layout.rows + ' rows x ' + layout.cols + ' columns = exactly ' +
    layout.count + ' GeoTIFF exports at 10 m.'
  );
  simple10Progress.setValue('Building the exact aligned 10 m export grid...');
  setStatus('Creating exactly ' + layout.count + ' Google Drive export tasks...', '#0d47a1');
  exactExportSetUi();

  simple10Service(function(done) {
    APP.roi.geometry().centroid(1, ee.Projection('EPSG:4326'))
      .coordinates().evaluate(done);
  }, function(coords, centreError) {
    if (generation !== EXACT_EXPORT.generation) return;
    if (centreError || !coords || coords.length < 2) {
      EXACT_EXPORT.busy = false;
      simple10Progress.setValue(lcErrorText(centreError || 'The AOI centre could not be read.'));
      exactExportSetUi();
      return;
    }
    var crs;
    try {
      crs = simple10Utm(Number(coords[0]), Number(coords[1]));
    } catch (projectionError) {
      EXACT_EXPORT.busy = false;
      simple10Progress.setValue(lcErrorText(projectionError));
      exactExportSetUi();
      return;
    }

    simple10Service(function(done) {
      APP.roi.geometry().bounds(1, ee.Projection(crs)).coordinates().evaluate(done);
    }, function(polygons, boundsError) {
      if (generation !== EXACT_EXPORT.generation) return;
      if (boundsError) {
        EXACT_EXPORT.busy = false;
        simple10Progress.setValue(lcErrorText(boundsError));
        exactExportSetUi();
        return;
      }
      try {
        var p = exactExportPlan(polygons && polygons[0], crs, layout);
        var image = ee.Image(APP.finalMap)
          .rename('classification')
          .toUint8()
          .clip(APP.roi.geometry())
          .unmask(0, false);
        var prefix = clean(prefixBox.getValue()) || 'landcover';

        for (var index = 0; index < p.cells; index++) {
          var tile = exactExportRoot(p, index);
          var name = prefix + '_' + APP.cfg.targetYear + '_seed' +
            APP.best.seed + '_R' + exactExportPad(tile.row) +
            '_C' + exactExportPad(tile.col) + '_10m';
          var region = ee.Geometry.Rectangle([
            tile.x0,
            tile.yTop - tile.height * 10,
            tile.x0 + tile.width * 10,
            tile.yTop
          ], ee.Projection(crs), false);

          Export.image.toDrive({
            image: image,
            description: name,
            folder: EXACT_DRIVE_FOLDER,
            fileNamePrefix: name,
            region: region,
            crs: crs,
            crsTransform: [10, 0, tile.x0, 0, -10, tile.yTop],
            maxPixels: 1e13,
            shardSize: 256,
            fileFormat: 'GeoTIFF',
            skipEmptyTiles: false,
            formatOptions: {cloudOptimized: true, noData: 0}
          });
        }

        EXACT_EXPORT.busy = false;
        simple10Summary.setValue(
          layout.rows + ' rows x ' + layout.cols + ' columns = exactly ' +
          layout.count + ' GeoTIFF files at 10 m.'
        );
        simple10Progress.setValue(
          'Exactly ' + layout.count + ' export tasks were created. Open the Earth Engine Tasks tab, run the tasks, and find the completed GeoTIFF files in the Google Drive folder "' +
          EXACT_DRIVE_FOLDER + '". Class values are 1-12 and NoData is 0.'
        );
        setStatus('Exactly ' + layout.count + ' Google Drive export tasks are ready.', '#1b5e20');
        exactExportSetUi();
      } catch (exportError) {
        EXACT_EXPORT.busy = false;
        simple10Progress.setValue(lcErrorText(exportError));
        setStatus('Export setup error: ' + lcErrorText(exportError), '#b71c1c');
        exactExportSetUi();
      }
    });
  });
}

exportButton.unlisten();
exportButton.onClick(exactExportToDrive);
tileButton.unlisten();

for (var exactExportUiIndex = 0;
     exactExportUiIndex < control.widgets().length();
     exactExportUiIndex++) {
  var exactExportWidget = control.widgets().get(exactExportUiIndex);
  if (exactExportWidget && typeof exactExportWidget.getValue === 'function') {
    var exactExportText = String(exactExportWidget.getValue());
    if (exactExportText.indexOf('Rows x columns') === 0 ||
        exactExportText.indexOf('Choose rows and columns') === 0 ||
        exactExportText.indexOf('The published App generates direct GeoTIFF') === 0) {
      exactExportWidget.setValue(
        'Rows x columns is the exact number of 10 m GeoTIFF exports. ' +
        'For example, 2 rows x 5 columns creates exactly 10 files. ' +
        'Exports are written to Google Drive without hidden subdivision.'
      );
    }
  }
}

var exactExportPreviousReset = simple10Reset;
simple10Reset = function(message) {
  exactExportPreviousReset(message);
  if (!APP.running && !CACHE10.preparing) {
    simple10Summary.setValue(simple10HasMap() ?
      'Map ready. Rows x columns will equal the exact number of Google Drive GeoTIFF exports.' :
      'Run automated mapping. Rows x columns will equal the exact number of Google Drive GeoTIFF exports.');
  }
  exactExportSetUi();
};

SIMPLE10.token++;
APP.downloadGeneration++;
SIMPLE10.busy = false;
SIMPLE10.plan = null;
SIMPLE10.pending = [];
SIMPLE10.active = null;
simple10Reset();
exactExportSetUi();

var FINAL_DIRECT = {BATCH_SIZE: 20, DEFAULT_ROWS: 53, DEFAULT_COLS: 131};

rowsBox.setValue(String(FINAL_DIRECT.DEFAULT_ROWS), false);
colsBox.setValue(String(FINAL_DIRECT.DEFAULT_COLS), false);
SIMPLE10.BATCH = FINAL_DIRECT.BATCH_SIZE;

function finalDirectSync() {
  var blocked = APP.running || CACHE10.preparing || SIMPLE10.busy;
  exportButton.setDisabled(blocked || !simple10HasMap());
  exportButton.setLabel(
    SIMPLE10.busy ? 'PAUSE LINK GENERATION' :
    SIMPLE10.failed ? 'RETRY CURRENT DOWNLOAD' :
    SIMPLE10.nextBatch ? 'GENERATE NEXT 20 DOWNLOAD LINKS' :
    SIMPLE10.finished ? 'REGENERATE DOWNLOAD LINKS' :
    SIMPLE10.plan ? 'CONTINUE DOWNLOAD LINKS' :
    'GENERATE FIRST 20 DOWNLOAD LINKS'
  );
  tileButton.setDisabled(true);
  tileButton.style().set('shown', false);
  [rowsBox, colsBox, prefixBox].forEach(function(widget) {
    widget.setDisabled(blocked);
  });
  simple10ModelWidgets.forEach(function(widget) {
    widget.setDisabled(APP.running || CACHE10.preparing);
  });
  scaleBox.setValue('10', false);
  scaleBox.setDisabled(true);
  runButton.setDisabled(APP.running || CACHE10.preparing);
}
simple10Sync = finalDirectSync;


var FINAL_DIRECT_MAX_SIDE = 10000;
var FINAL_DIRECT_MAX_PIXELS = 24 * 1024 * 1024;
var finalDirectExtentPlan = cache10OriginalPlan;
simple10Plan = function(ring, crs, layout) {
  var p = finalDirectExtentPlan(ring, crs, layout);
  p.rows = layout.rows;
  p.cols = layout.cols;
  p.cells = layout.rows * layout.cols;
  p.files = p.cells;
  p.prepared = !!CACHE10.loadedAsset;

  var widest = Math.ceil(p.width / p.cols);
  var tallest = Math.ceil(p.height / p.rows);
  var pixels = widest * tallest;
  if (widest > FINAL_DIRECT_MAX_SIDE ||
      tallest > FINAL_DIRECT_MAX_SIDE ||
      pixels > FINAL_DIRECT_MAX_PIXELS) {
    var minColsSide = Math.ceil(p.width / FINAL_DIRECT_MAX_SIDE);
    var minRowsSide = Math.ceil(p.height / FINAL_DIRECT_MAX_SIDE);
    var minColsPixels = Math.ceil(
      p.width / Math.max(1, Math.floor(FINAL_DIRECT_MAX_PIXELS / tallest))
    );
    var minRowsPixels = Math.ceil(
      p.height / Math.max(1, Math.floor(FINAL_DIRECT_MAX_PIXELS / widest))
    );
    var suggestedRows = Math.max(layout.rows, minRowsSide, minRowsPixels);
    var suggestedCols = Math.max(layout.cols, minColsSide, minColsPixels);
    throw new Error(
      'The selected ' + layout.rows + ' x ' + layout.cols +
      ' grid is too large for direct 10 m browser downloads. Use at least ' +
      suggestedRows + ' rows x ' + suggestedCols + ' columns. ' +
      'The default 53 x 131 grid is recommended for this AOI.'
    );
  }
  return p;
};

simple10Part = function(root, index) {
  if (index !== 0) {
    throw new Error('Only one GeoTIFF is allowed for each requested grid cell.');
  }
  return simple10Tile({
    row: root.row,
    col: root.col,
    id: root.id,
    label: 'Row ' + root.row + ', column ' + root.col,
    x0: root.x0,
    yTop: root.yTop,
    width: root.width,
    height: root.height
  });
};
simple10TakeNext = function() {
  if (SIMPLE10.pending.length) {
    throw new Error('Unexpected hidden subdivision was detected.');
  }
  if (!SIMPLE10.plan || SIMPLE10.rootIndex >= SIMPLE10.plan.cells) return null;
  var root = simple10Root(SIMPLE10.rootIndex++);
  return simple10Part(root, 0);
};
simple10CanSplit = function() { return false; };
simple10Split = function() {
  throw new Error('Automatic subdivision is disabled. Increase rows and columns instead.');
};
simple10SummaryText = function() {
  var p = SIMPLE10.plan;
  return p.rows + ' rows x ' + p.cols + ' columns = exactly ' + p.cells +
    ' direct 10 m GeoTIFF ZIP downloads. Links are shown 20 at a time. ' +
    'Classes are 1-12; outside/missing pixels are 0.';
};

for (var finalDirectUiIndex = 0;
     finalDirectUiIndex < control.widgets().length();
     finalDirectUiIndex++) {
  var finalDirectWidget = control.widgets().get(finalDirectUiIndex);
  if (finalDirectWidget && typeof finalDirectWidget.getValue === 'function') {
    var finalDirectText = String(finalDirectWidget.getValue());
    if (finalDirectText.indexOf('Rows x columns') === 0 ||
        finalDirectText.indexOf('Choose rows and columns') === 0 ||
        finalDirectText.indexOf('The published App generates direct GeoTIFF') === 0) {
      finalDirectWidget.setValue(
        'Use the recommended 53 rows x 131 columns for this large AOI. ' +
        'The App generates direct 10 m GeoTIFF ZIP links in pages of 20. ' +
        'The user needs only this interface; no Tasks panel or Google Drive is required.'
      );
    }
  }
}
for (var finalDirectHintIndex = 0;
     finalDirectHintIndex < simple10Host.widgets().length();
     finalDirectHintIndex++) {
  var finalDirectHint = simple10Host.widgets().get(finalDirectHintIndex);
  if (finalDirectHint && typeof finalDirectHint.getValue === 'function') {
    var finalDirectHintText = String(finalDirectHint.getValue());
    if (finalDirectHintText.indexOf('Pixels stay 10 m') === 0 ||
        finalDirectHintText.indexOf('If opening a download link fails') === 0) {
      finalDirectHint.setValue(
        'Download every link on the current page, then click GENERATE NEXT 20 DOWNLOAD LINKS. ' +
        'All files use the same aligned 10 m grid and can be mosaicked in QGIS.'
      );
    }
  }
}

exportButton.unlisten();
exportButton.onClick(simple10Click);
tileButton.unlisten();
tileButton.setDisabled(true);
tileButton.style().set('shown', false);

EXACT_EXPORT.busy = false;
EXACT_EXPORT.generation++;
SIMPLE10.token++;
APP.downloadGeneration++;
SIMPLE10.busy = false;
SIMPLE10.plan = null;
SIMPLE10.rootIndex = 0;
SIMPLE10.partIndex = 0;
SIMPLE10.pending = [];
SIMPLE10.active = null;
SIMPLE10.ready = 0;
SIMPLE10.batchReady = 0;
SIMPLE10.nextBatch = false;
SIMPLE10.failed = false;
SIMPLE10.finished = false;
simple10Links.clear();
simple10Progress.setValue('');
simple10Summary.setValue(
  simple10HasMap() ?
    'Map ready. Recommended grid: 53 rows x 131 columns. Generate the first 20 direct links.' :
    'Run automated mapping. Recommended download grid: 53 rows x 131 columns.'
);
simple10Mount();
finalDirectSync();

SIMPLE10.EDGE = FINAL_DIRECT_MAX_SIDE;
SIMPLE10.MIN_EDGE = 64;
SIMPLE10.BATCH = FINAL_DIRECT.BATCH_SIZE;

// Reset only the download cursor. The completed map and all results are retained.
SIMPLE10.token++;
APP.downloadGeneration++;
SIMPLE10.busy = false;
SIMPLE10.plan = null;
SIMPLE10.rootIndex = 0;
SIMPLE10.partIndex = 0;
SIMPLE10.pending = [];
SIMPLE10.active = null;
SIMPLE10.ready = 0;
SIMPLE10.batchReady = 0;
SIMPLE10.nextBatch = false;
SIMPLE10.failed = false;
SIMPLE10.finished = false;
simple10Links.clear();
simple10Progress.style().set('color', '#0d47a1');
simple10Progress.setValue('');
simple10Summary.setValue(
  simple10HasMap() ?
    'Map ready. Generate the first 20 direct 10 m download links.' :
    'Run automated mapping, then generate direct 10 m download links.'
);
simple10Mount();
exportButton.unlisten();
exportButton.onClick(simple10Click);
finalDirectSync();

var VALID10 = {
  empty: 0,
  checked: 0,
  downloadable: 0
};

function valid10TileGeometry(tile, crs) {
  return ee.Geometry.Rectangle([
    tile.x0,
    tile.yTop - tile.height * 10,
    tile.x0 + tile.width * 10,
    tile.yTop
  ], ee.Projection(crs), false);
}

function valid10ClassificationImage() {
  var raw = ee.Image(APP.finalMap).rename('classification').toUint8();
  var validMask = raw.gte(1).and(raw.lte(12));
  return raw.updateMask(validMask);
}

function valid10Next(token) {
  if (!simple10Current(token) || !SIMPLE10.busy) return;

  if (!simple10Remaining()) {
    SIMPLE10.busy = false;
    SIMPLE10.finished = true;
    simple10Progress.style().set('color', '#1b5e20');
    simple10Progress.setValue(
      'Finished checking the complete grid. ' + VALID10.downloadable +
      ' classified download links were prepared and ' + VALID10.empty +
      ' outside-AOI or empty cells were skipped. Only files containing classes 1-12 were offered.'
    );
    simple10Sync();
    return;
  }

  if (SIMPLE10.batchReady >= SIMPLE10.BATCH) {
    SIMPLE10.busy = false;
    SIMPLE10.nextBatch = true;
    simple10Progress.style().set('color', '#0d47a1');
    simple10Progress.setValue(
      SIMPLE10.batchReady + ' valid classified links are ready on this page. ' +
      'Download them, then click GENERATE NEXT 20 DOWNLOAD LINKS. ' +
      VALID10.empty + ' empty/outside-AOI cells have been skipped so far.'
    );
    simple10Sync();
    return;
  }

  if (!SIMPLE10.active) {
    var nextTile = simple10TakeNext();
    if (!nextTile) {
      SIMPLE10.busy = false;
      SIMPLE10.finished = true;
      simple10Sync();
      return;
    }
    var nextWidget = ui.Label(nextTile.label + ' - checking for classified pixels...', {
      fontSize: '11px', whiteSpace: 'pre-wrap'
    });
    SIMPLE10.active = {tile: nextTile, widget: nextWidget, tries: 0};
    simple10Links.add(nextWidget);
  }

  var active = SIMPLE10.active;
  active.tries++;
  active.widget.setValue(active.tile.label + ' - checking for classified pixels...');
  simple10Progress.style().set('color', '#0d47a1');
  simple10Progress.setValue(
    'Checking grid cell ' + (VALID10.checked + 1) + ' of ' + SIMPLE10.plan.cells +
    '. Empty cells are skipped automatically; only classified tiles receive links.'
  );

  var tile = simple10Tile(active.tile);
  var tileGeometry = valid10TileGeometry(tile, SIMPLE10.plan.crs);
  var clippedGeometry = tileGeometry.intersection(APP.roi.geometry(), 1);
  var classified = valid10ClassificationImage();

  simple10Service(function(done) {
    ee.Dictionary({
      intersectionArea: clippedGeometry.area(1),
      validPixels: classified.mask().reduceRegion({
        reducer: ee.Reducer.sum(),
        geometry: clippedGeometry,
        crs: SIMPLE10.plan.crs,
        scale: 10,
        maxPixels: FINAL_DIRECT_MAX_PIXELS,
        bestEffort: false,
        tileScale: 4
      }).get('classification')
    }).evaluate(done);
  }, function(check, checkError) {
    if (!simple10Current(token) || !SIMPLE10.busy) return;
    if (checkError) {
      if (active.tries >= 2) {
        simple10StopWithError(token, checkError, false);
        return;
      }
      ui.util.setTimeout(function() { valid10Next(token); }, 150);
      return;
    }

    VALID10.checked++;
    var area = check ? Number(check.intersectionArea || 0) : 0;
    var validPixels = check ? Number(check.validPixels || 0) : 0;

    if (!(area > 0) || !(validPixels > 0)) {
      VALID10.empty++;
      active.widget.setValue(active.tile.label + ' - skipped: outside AOI or no classified pixels.');
      active.widget.style().set({color: '#777777', textDecoration: 'none'});
      SIMPLE10.active = null;
      ui.util.setTimeout(function() { valid10Next(token); }, 25);
      return;
    }

    active.widget.setValue(active.tile.label + ' - preparing classified GeoTIFF...');
    var name = (clean(prefixBox.getValue()) || 'landcover') + '_' +
      APP.cfg.targetYear + '_seed' + APP.best.seed + '_' +
      SIMPLE10.plan.rows + 'x' + SIMPLE10.plan.cols + '_' + tile.id + '_10m';

    simple10Service(function(done) {
      classified.unmask(0, false).getDownloadURL({
        name: name,
        crs: SIMPLE10.plan.crs,
        crs_transform: [10, 0, tile.x0, 0, -10, tile.yTop],
        dimensions: [tile.width, tile.height],
        filePerBand: false,
        format: 'ZIPPED_GEO_TIFF'
      }, done);
    }, function(url, downloadError) {
      if (!simple10Current(token) || !SIMPLE10.busy) return;
      if (!downloadError && typeof url === 'string' && /^https:\/\//.test(url)) {
        active.widget.setValue(active.tile.label + ' - Download classified GeoTIFF (ZIP)');
        active.widget.setUrl(url);
        active.widget.style().set({color: '#0b57d0', textDecoration: 'underline'});
        SIMPLE10.active = null;
        SIMPLE10.ready++;
        SIMPLE10.batchReady++;
        VALID10.downloadable++;
        ui.util.setTimeout(function() { valid10Next(token); }, 100);
        return;
      }
      if (active.tries >= 2) {
        simple10StopWithError(token, downloadError || 'No valid download URL was returned.', false);
        return;
      }
      ui.util.setTimeout(function() { valid10Next(token); }, 150);
    });
  });
}

// Replace the previous queue with the verified non-empty-tile queue.
simple10Next = valid10Next;

var valid10PreviousReset = simple10Reset;
simple10Reset = function(message) {
  VALID10.empty = 0;
  VALID10.checked = 0;
  VALID10.downloadable = 0;
  valid10PreviousReset(message);
};

// Clear stale links produced by the previous version.
SIMPLE10.token++;
APP.downloadGeneration++;
SIMPLE10.busy = false;
SIMPLE10.plan = null;
SIMPLE10.rootIndex = 0;
SIMPLE10.partIndex = 0;
SIMPLE10.pending = [];
SIMPLE10.active = null;
SIMPLE10.ready = 0;
SIMPLE10.batchReady = 0;
SIMPLE10.nextBatch = false;
SIMPLE10.failed = false;
SIMPLE10.finished = false;
simple10Links.clear();
simple10Progress.style().set('color', '#0d47a1');
simple10Progress.setValue('');
simple10Summary.setValue(
  simple10HasMap() ?
    'Map ready. Empty/outside-AOI grid cells will be skipped automatically. Only tiles containing classes 1-12 will receive download links.' :
    'Run automated mapping. Empty/outside-AOI grid cells will be skipped automatically during download preparation.'
);
for (var valid10HintIndex = 0;
     valid10HintIndex < simple10Host.widgets().length();
     valid10HintIndex++) {
  var valid10Hint = simple10Host.widgets().get(valid10HintIndex);
  if (valid10Hint && typeof valid10Hint.getValue === 'function') {
    var valid10HintText = String(valid10Hint.getValue());
    if (valid10HintText.indexOf('Download every link') === 0) {
      valid10Hint.setValue(
        'Grey entries are outside the AOI or contain no classified pixels and should not be downloaded. ' +
        'Blue links contain valid class values 1-12. Download the blue links, then generate the next page.'
      );
    }
  }
}
simple10Mount();
exportButton.unlisten();
exportButton.onClick(simple10Click);
finalDirectSync();
// END FINAL VERIFIED CLASS-DATA DOWNLOAD CORRECTION
// ============================================================================
