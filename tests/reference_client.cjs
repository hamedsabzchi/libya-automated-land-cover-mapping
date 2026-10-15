// Read-only oracle: execute only pure client helpers extracted from pinned GEE.
// Never initialize Earth Engine or evaluate the application/UI.
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');
const source = fs.readFileSync(path.join(__dirname, '../gee/automated_land_cover_app.js'), 'utf8');
function between(start, end, text=source) {
  const first = text.indexOf(start);
  if (first < 0) throw Error('Missing reference anchor: ' + start);
  const last = text.indexOf(end, first + start.length);
  if (last < 0) throw Error('Missing reference end: ' + end);
  return text.slice(first, last);
}
const ctx = vm.createContext({classValues: Array.from({length:12}, (_, i)=>i+1)});
vm.runInContext(between('function flexibleAssetId(', 'var flexibleAssetReadConfig'), ctx);
vm.runInContext(between('function flexibleBuildClassLookup(', 'function flexibleNormalizeTraining('), ctx);
const run = source.slice(source.indexOf('function flexibleRunCompleteAssets()'));
const scoring = between('var producer = Array.isArray(data.prod)', 'if (!scoredClasses)', run);
vm.runInContext('function referenceScore(data,cfg){' + scoring +
  'return {score:minimumAccuracy,targetReached:targetReached,scored:scoredClasses};}', ctx);
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const output = input.map(item => {
  try {
    let result;
    if (item.kind === 'asset') result = ctx.flexibleAssetId(item.value, 'Asset');
    else if (item.kind === 'classes') result = ctx.flexibleBuildClassLookup(item.value);
    else if (item.kind === 'score') result = ctx.referenceScore(item.value, {excluded:8,targetAccuracy:60});
    else throw Error('Unknown oracle request');
    return {ok:true,result};
  } catch(error) { return {ok:false}; }
});
process.stdout.write(JSON.stringify(output));
