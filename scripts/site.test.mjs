import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {mapAxis,normalize,reflectRGBA} from '../site/mirror.mjs';
test('a right-half mirror uses the unchanged left half',()=>{
  const pixels=Uint8ClampedArray.from([1,2,3,255,4,5,6,255,7,8,9,255,10,11,12,255]);
  assert.deepEqual([...reflectRGBA(pixels,4,1,{mask:2,width:2,height:2})],[1,2,3,255,4,5,6,255,4,5,6,255,1,2,3,255]);
});
test('all 44 exposed settings map into unchanged original source regions',()=>{
  let count=0;
  for(const mask of [1,2,4,8,3,12,15])for(let width=2;width<=6;width++)for(let height=2;height<=6;height++){
    if(!(mask&3)&&width!==2||!(mask&12)&&height!==2||(mask&3)===3&&width===2||(mask&12)===12&&height===2)continue;
    assert.deepEqual(normalize({mask,width,height}),{mask,width,height});
    for(let x=0;x<96;x++){
      const at=mapAxis(x,96,width,mask&1,mask&2);assert.ok(at>=0&&at<96);assert.equal(mapAxis(at,96,width,mask&1,mask&2),at);
    }
    for(let y=0;y<64;y++){
      const at=mapAxis(y,64,height,mask&4,mask&8);assert.ok(at>=0&&at<64);assert.equal(mapAxis(at,64,height,mask&4,mask&8),at);
    }
    count++;
  }
  assert.equal(count,44);
});
test('paired halves are adjusted; unknown settings are rejected',()=>{
  assert.deepEqual(normalize({mask:15,width:2,height:2}),{mask:15,width:3,height:3});
  assert.throws(()=>normalize({mask:7,width:3,height:3}),RangeError);
});
test('compatibility, honest illustration label and download are present',async()=>{
  const html=await readFile(new URL('../site/index.html',import.meta.url),'utf8');
  for(const phrase of ['original Canon EOS M','2.0.2','2025-06-20','AI-generated','MIRROR-0.2.0-EOSM202.zip','normal shutter button'])assert.ok(html.includes(phrase),phrase);
  assert.ok(!html.includes('https://unpkg.com'));assert.ok(!html.includes('analytics'));
});
