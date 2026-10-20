export const placements = new Map([[1,'Left'],[2,'Right'],[4,'Top'],[8,'Bottom'],[3,'Left + Right'],[12,'Top + Bottom'],[15,'All edges']]);
export const fractions = new Map([[2,'Half'],[3,'Third'],[4,'Quarter'],[5,'Fifth'],[6,'Sixth']]);
export function normalize({mask,width,height}) {
  if (!placements.has(mask) || !fractions.has(width) || !fractions.has(height)) throw new RangeError('Unknown mirror setting');
  return {mask,width:(mask&3)===3&&width===2?3:width,height:(mask&12)===12&&height===2?3:height};
}
export function mapAxis(at,extent,divisor,low,high) {
  const border=Math.floor(extent/divisor);
  if(low&&at<border)return 2*border-1-at;
  if(high&&at>=extent-border)return 2*(extent-border)-1-at;
  return at;
}
// Browser illustration of the folds. This is not a camera/RAW emulator.
export function reflectRGBA(source,width,height,settings) {
  const s=normalize(settings),target=new Uint8ClampedArray(source.length);
  for(let y=0;y<height;y++) {
    const sy=mapAxis(y,height,s.height,s.mask&4,s.mask&8);
    for(let x=0;x<width;x++) {
      const sx=mapAxis(x,width,s.width,s.mask&1,s.mask&2),a=(sy*width+sx)*4,b=(y*width+x)*4;
      target[b]=source[a];target[b+1]=source[a+1];target[b+2]=source[a+2];target[b+3]=source[a+3];
    }
  }
  return target;
}
