import {placements,fractions,normalize,reflectRGBA} from './mirror.mjs';
const source=new Image();source.src='assets/seaside-scene.webp';
const demo=document.querySelector('#demo'),widthSelect=document.querySelector('#width'),heightSelect=document.querySelector('#height');
const compare=document.querySelector('#compare'),caption=document.querySelector('#demo-caption');
let settings={mask:15,width:4,height:4},original=false,currentImage=source,ready=false,uploadURL;
function pixels(image,width,height){
  const surface=document.createElement('canvas');surface.width=width;surface.height=height;
  const context=surface.getContext('2d',{willReadFrequently:true});
  const scale=Math.max(width/image.naturalWidth,height/image.naturalHeight),sw=width/scale,sh=height/scale;
  context.drawImage(image,(image.naturalWidth-sw)/2,(image.naturalHeight-sh)/2,sw,sh,0,0,width,height);
  return context.getImageData(0,0,width,height);
}
function draw(canvas,image,state,showOriginal=false){
  const data=pixels(image,canvas.width,canvas.height),result=showOriginal?data:new ImageData(reflectRGBA(data.data,data.width,data.height,state),data.width,data.height);
  canvas.getContext('2d').putImageData(result,0,0);canvas.hidden=false;
  const fallback=canvas.previousElementSibling;if(fallback?.tagName==='IMG')fallback.hidden=true;
}
function update(){
  settings=normalize(settings);
  for(const button of document.querySelectorAll('[data-mask]'))button.setAttribute('aria-pressed',String(Number(button.dataset.mask)===settings.mask));
  for(const [select,key,used,paired] of [[widthSelect,'width',settings.mask&3,(settings.mask&3)===3],[heightSelect,'height',settings.mask&12,(settings.mask&12)===12]]){
    select.disabled=!used;select.value=String(settings[key]);select.options[0].disabled=paired;
    select.setAttribute('aria-label',`${key==='width'?'Width':'Height'}${used?'':' — not used for this layout'}`);
  }
  const parts=[placements.get(settings.mask)];if(settings.mask&3)parts.push(fractions.get(settings.width));if(settings.mask&12)parts.push(fractions.get(settings.height));
  const label=parts.join(' · ');caption.textContent=original?'Original scene':label;
  compare.textContent=original?'Show mirror ↔':'Show original ↔';compare.setAttribute('aria-pressed',String(original));
  demo.setAttribute('aria-label',`${original?'Original scene':`Illustrative mirror preview: ${label}`}`);
  if(ready)draw(demo,currentImage,settings,original);
}
for(const button of document.querySelectorAll('[data-mask]'))button.addEventListener('click',()=>{settings.mask=Number(button.dataset.mask);original=false;update();});
widthSelect.addEventListener('change',()=>{settings.width=Number(widthSelect.value);original=false;update();});
heightSelect.addEventListener('change',()=>{settings.height=Number(heightSelect.value);original=false;update();});
compare.addEventListener('click',()=>{original=!original;update();});
for(const node of document.querySelectorAll('[data-diagram]')){
  const m=Number(node.dataset.diagram),rects=[];
  if(m&1)rects.push('<rect x="1" y="1" width="7" height="18"/>');if(m&2)rects.push('<rect x="20" y="1" width="7" height="18"/>');
  if(m&4)rects.push('<rect x="1" y="1" width="26" height="5"/>');if(m&8)rects.push('<rect x="1" y="14" width="26" height="5"/>');
  node.innerHTML=`<svg viewBox="0 0 28 20" fill="none"><rect x=".5" y=".5" width="27" height="19" stroke="currentColor"/><g fill="currentColor" opacity=".6">${rects.join('')}</g></svg>`;
}
source.addEventListener('load',()=>{
  for(const canvas of document.querySelectorAll('[data-preset]')){const [mask,width,height]=canvas.dataset.preset.split(',').map(Number);draw(canvas,source,{mask,width,height});}
  if(currentImage===source){ready=true;compare.disabled=false;update();}
});
source.addEventListener('error',()=>{document.querySelector('#upload-status').textContent='The sample image could not load. You can try your own photo.';});
document.querySelector('#photo-upload').addEventListener('change',event=>{
  const file=event.target.files?.[0],status=document.querySelector('#upload-status');if(!file)return;
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)){status.textContent='Please choose a JPG, PNG or WebP image.';return;}
  if(file.size>25*1024*1024){status.textContent='Please choose an image smaller than 25 MB.';return;}
  const image=new Image(),url=URL.createObjectURL(file);
  image.onload=()=>{if(uploadURL)URL.revokeObjectURL(uploadURL);uploadURL=url;currentImage=image;ready=true;original=false;compare.disabled=false;status.textContent='Your photo · stays in your browser · 3:2 preview';update();};
  image.onerror=()=>{URL.revokeObjectURL(url);status.textContent='That image could not be opened. Try another JPG, PNG or WebP.';};image.src=url;
});
update();
