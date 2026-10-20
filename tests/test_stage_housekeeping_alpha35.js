"use strict";
// Focused pure-function UI test; does not connect to Docker or mutate staging.
const fs=require("node:fs");
const vm=require("node:vm");
const assert=require("node:assert/strict");
const root=require("node:path").join(__dirname,"..","server","ui");
const app=fs.readFileSync(require("node:path").join(root,"app.js"),"utf8");
const html=fs.readFileSync(require("node:path").join(root,"index.html"),"utf8");
const beginning=app.indexOf("function compiledHousekeepingPageData(");
const ending=app.indexOf("\nfunction compiledHousekeepingRender()",beginning);
assert.ok(beginning>0 && ending>beginning);
const ctx={};
vm.runInNewContext(
  "const COMPILED_HOUSEKEEPING_PAGE_SIZE=8;\n"+
  app.slice(beginning,ending)+
  "\nthis.pageData=compiledHousekeepingPageData;",ctx);
const ids=Array.from({length:15},(_,i)=>
  "osd-compiled-"+String(i).padStart(12,"0"));
let value=ctx.pageData(ids,"",0);
assert.equal(value.total,15);
assert.equal(value.pages,2);
assert.equal(value.entries.length,8);
assert.equal(value.entries[0],ids[0]);
value=ctx.pageData(ids,"",1);
assert.equal(value.entries.length,7);
assert.equal(value.entries[0],ids[8]);
value=ctx.pageData(ids,"",300);
assert.equal(value.current,1);
value=ctx.pageData(ids,"00000000001",0);
assert.equal(value.total,6);
assert.ok(value.entries.every(id=>id.includes("00000000001")));
value=ctx.pageData(ids,"unmatched",0);
assert.equal(value.total,0);
assert.equal(value.pages,0);
assert.equal(value.current,0);
assert.equal(value.entries.length,0);
for(const id of ["compiled-housekeeping","compiled-housekeeping-list",
    "compiled-housekeeping-search","compiled-housekeeping-total",
    "compiled-housekeeping-status","compiled-housekeeping-prev",
    "compiled-housekeeping-next","compiled-housekeeping-page"]){
 assert.equal(html.split('id="'+id+'"').length,2);
}
assert.ok(html.indexOf('id="compiled-list"')<
          html.indexOf('id="compiled-housekeeping-list"'));
assert.ok(html.indexOf("<details id=\"compiled-housekeeping\"")>0);
assert.ok(app.includes("compiledHousekeepingDirectories=orphaned.slice().sort()"));
assert.ok(!app.includes("orphaned.slice(0,6)"));
console.log("HOUSEKEEPING_PAGINATION_FILTER_ISOLATION_PASS 15 directories 2 pages");
