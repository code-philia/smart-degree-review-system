"""Independent original-ink diagram facts and body relations for rule 15.

Region recovery is candidate preparation, never a usage decision. Existing
parser/index/figure consumers do not receive these additional physical facts.
"""
import re,unicodedata,math
from .usage_text_cache import normalize_text
from .usage_scope import usage_scope_map,usage_scope_identity

def _text(value):return re.sub(r'\s+','',unicodedata.normalize('NFKC',normalize_text(value))).casefold()
def _inside(a,b,margin=0):return b[0]-margin<=a[0] and b[1]-margin<=a[1] and a[2]<=b[2]+margin and a[3]<=b[3]+margin
def _union(boxes):return [min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)]
def _touch(a,b,margin=2):return max(a[0],b[0])<=min(a[2],b[2])+margin and max(a[1],b[1])<=min(a[3],b[3])+margin

def diagram_title_candidate(title):
 value=normalize_text(title)
 return bool(re.search(r'卷积.{0,10}(?:运算|操作).{0,10}(?:示例|示意)|convolution.{0,15}(?:example|illustration)|'
                       r'(?:GCN|图卷积).{0,15}(?:消息|传播|message|passing)|LoRA.{0,15}(?:微调|tuning)|'
                       r'(?:Softmax|低秩|low.?rank).{0,30}(?:注意力|attention).{0,30}(?:对比|comparison)',value,re.I))

def diagram_graphic_regions(index,groups,regions=None):
 """Recover source-bound closed physical regions; return independent dicts."""
 from .usage_figure_evidence import _full_title
 scopes=usage_scope_map(index.document);pages={p.number:p for p in index.document.pages};answer={}
 candidates=[]
 for ordinal,group in enumerate(groups):
  if not group or group[0].line.page_number not in pages or usage_scope_identity(scopes,group[0])[0]!='body':continue
  page=pages[group[0].line.page_number];title,caption=_full_title(group,page,'figure')
  if diagram_title_candidate(title):candidates.append((ordinal,group,page,title,caption))
 if not candidates:return answer
 try:
  import pymupdf
  with pymupdf.open(index.document.path) as pdf:
   for ordinal,group,page,title,caption in candidates:
    if not 1<=page.number<=len(pdf):continue
    original=pdf[page.number-1];bottom=min(r.bbox[1] for r in caption)-2
    ceiling=[0,page.height*.09,page.width,bottom]
    # A nearby embedded raster already has a physical boundary independent
    # of the caption's words and surrounding ordinary paragraphs.
    images={tuple(b) for i in original.get_images(full=True) for b in original.get_image_rects(i[0])
            if _inside(tuple(b),ceiling) and 0<=bottom-b.y1<=45 and b.width>60 and b.height>45}
    if len(images)==1:box=list(next(iter(images)))
    else:
     drawings=[d for d in original.get_drawings() if _inside(tuple(d['rect']),ceiling)]
     seed=[a['bbox'] for a in (regions or {}).get(ordinal,[]) if a['page_number']==page.number]
     if seed:
      selected=[d for d in drawings if any(_touch(tuple(d['rect']),b) for b in seed)]
      for _ in range(len(drawings)):
       grown=[d for d in drawings if d not in selected and any(_touch(tuple(d['rect']),tuple(s['rect']),5) for s in selected)]
       if not grown:break
       selected.extend(grown)
      if not selected:continue
      box=_union([tuple(d['rect']) for d in selected])
     else:
      # Two diagram headers align over two separately drawn projections.
      # Their original native positions bound the region; prose above these
      # headers never expands the region into a mathematical paragraph.
      labels=[r for r in page.lines if r.source=='native' and _inside(r.bbox,ceiling)]
      outputs=[r for r in labels if _text(r.text)=='output']
      projections=[r for r in labels if _text(r.text) in {'linear','bottleneckmlp'}]
      if len(outputs)!=2 or len(projections)!=2 or abs(outputs[0].bbox[1]-outputs[1].bbox[1])>3 or abs(projections[0].bbox[1]-projections[1].bbox[1])>3:continue
      low=min(r.bbox[1] for r in outputs)-2
      selected=[d for d in drawings if d['rect'].y0>=low and d['rect'].y1<=bottom]
      if not selected:continue
      box=_union([tuple(d['rect']) for d in selected]+[r.bbox for r in outputs+projections])
    if not _inside(box,ceiling) or box[2]-box[0]<60 or box[3]-box[1]<45:continue
    if any(other!=ordinal and usage_scope_identity(scopes,other_group[0])==usage_scope_identity(scopes,group[0])
           and other_group[0].line.page_number==page.number and _inside(other_group[0].line.bbox,box)
           for other,other_group in enumerate(groups) if other_group):continue
    # Ordinary independent prose cannot be absorbed as a graphic field.
    if any(r.source=='native' and len(r.text.strip())>=55 and _inside(r.bbox,box) for r in page.lines):continue
    answer[ordinal]=[dict(page_number=page.number,bbox=box,title=title,
      caption_keys=[dict(page_number=r.page_number,bbox=list(r.bbox)) for r in caption])]
 except (ImportError,OSError,RuntimeError,ValueError):return {}
 return answer

def diagram_native_fields(index,regions):
 """Exact index native ink in the independently recovered source regions."""
 from .usage_figure_evidence import _native_fields_in_regions
 return _native_fields_in_regions(index,regions)

def _center(box):return ((box[0]+box[2])/2,(box[1]+box[3])/2)
def _distance(a,b):return math.hypot(a[0]-b[0],a[1]-b[1])

def _original_ink(document,area):
 """Observe actual painted pixels (including source masks) and vector paths."""
 import pymupdf,numpy as np
 from pathlib import Path
 from hashlib import sha256
 try:
  digest=sha256(Path(document.path).read_bytes()).hexdigest()
  with pymupdf.open(document.path) as pdf:
   page=pdf[area['page_number']-1];box=area['bbox']
   drawings=[d for d in page.get_drawings() if _inside(tuple(d['rect']),box,.02)]
   pix=page.get_pixmap(matrix=pymupdf.Matrix(3,3),clip=pymupdf.Rect(box),colorspace=pymupdf.csRGB,alpha=False)
   rgb=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3).copy()
   return dict(pdf_sha=digest,page_number=area['page_number'],bbox=list(box),drawings=drawings,rgb=rgb,
               raster_origin=[pix.x,pix.y],render_scale=3)
 except (ImportError,OSError,RuntimeError,ValueError,IndexError):return None

def _polygon_tip(points):
 """Concave four-vertex arrowheads have an observable opposite tip."""
 if len(points)!=4:return None
 cross=[]
 for i,p in enumerate(points):
  a=points[i-1];b=points[(i+1)%4];cross.append((p[0]-a[0])*(b[1]-p[1])-(p[1]-a[1])*(b[0]-p[0]))
 positive=[i for i,x in enumerate(cross) if x>1e-4];negative=[i for i,x in enumerate(cross) if x< -1e-4]
 odd=positive if len(positive)==1 else negative if len(negative)==1 else []
 if not odd:return None
 return points[(odd[0]+2)%4],points[odd[0]]

def _vector_graph(ink,blocks=()):
 """Use actual endpoints and arrowhead direction; crossings are not junctions."""
 ds=ink['drawings'];circles=[];paths=[];heads=[]
 for d in ds:
  box=tuple(d['rect']);w,h=box[2]-box[0],box[3]-box[1];items=d['items']
  if d['type']=='fs' and 12<w<60 and .98<w/max(h,.001)<1.02 and len(items)>=4 and all(i[0]=='c' for i in items):
   if not any(_distance(_center(box),_center(b))<.5 for b in circles):circles.append(box)
  if d.get('fill') is not None and len(items)==4 and all(i[0]=='l' for i in items) and max(w,h)<15:
   points=[tuple(i[1]) for i in items];tip=_polygon_tip(points)
   if tip and not any(_distance(tip[0],old[0])<.2 for old in heads):heads.append(tip)
 for d in ds:
  if d['type']!='s' or not d['items'] or not all(i[0]=='l' for i in d['items']):continue
  if any(_inside(tuple(d['rect']),b,.1) for b in circles):continue
  items=d['items']
  if any(_distance(tuple(a[2]),tuple(b[1]))>.3 for a,b in zip(items,items[1:])):continue
  points=[tuple(items[0][1]),*[tuple(i[2]) for i in items]]
  if sum(_distance(a,b) for a,b in zip(points,points[1:]))<6:continue
  if not any(points==old for old in paths):paths.append(points)
 nodes=[dict(kind='circle',bbox=list(b)) for b in circles]+[dict(b) for b in blocks]
 def node_at(point,output=False):
  found=[]
  for i,node in enumerate(nodes):
   b=node['bbox'];cx,cy=_center(b)
   if node['kind']=='circle':gap=abs(_distance(point,(cx,cy))-(b[2]-b[0])/2);ok=gap<=3
   elif node['kind']=='output':ok=output and b[0]-2<=point[0]<=b[2]+2 and 0<=point[1]-b[3]<=15
   else:ok=_inside([*point,*point],b,3) and min(abs(point[0]-b[0]),abs(point[0]-b[2]),abs(point[1]-b[1]),abs(point[1]-b[3]))<=3
   if ok:found.append(i)
  return found[0] if len(found)==1 else None
 edges=[];unbound=[];unresolved=[]
 for tip,base in heads:
  candidates=[]
  for k,points in enumerate(paths):
   for reverse in (False,True):
    chain=list(reversed(points)) if reverse else points
    if _distance(chain[-1],base)<=1.6:candidates.append((k,chain))
  if len(candidates)!=1:unresolved.append(dict(tip=list(tip),reason='shaft_not_unique'));continue
  key,chain=candidates[0];used={key};start=chain[0];source=node_at(start)
  for _ in range(8):
   if source is not None:break
   more=[]
   for k,points in enumerate(paths):
    if k in used:continue
    for reverse in (False,True):
     previous=list(reversed(points)) if reverse else points
     if _distance(previous[-1],start)<.4:more.append((k,previous))
   if len(more)!=1:break
   k,previous=more[0];used.add(k);chain=previous+chain[1:];start=chain[0];source=node_at(start)
  dest=node_at(tip,True)
  if source is None and dest is not None:
   unbound.append(dict(target=dest,tail=list(start),tip=list(tip),path=[list(p) for p in chain]));continue
  if source is None or dest is None or source==dest:
   unresolved.append(dict(tip=list(tip),tail=list(start),reason='endpoints_not_bound'));continue
  edges.append(dict(source=source,target=dest,tail=list(start),tip=list(tip),path=[list(p) for p in chain]))
 uninterpreted=[]
 for d in ds:
  if d['type']!='s' or all(i[0]=='l' for i in d['items']):continue
  b=tuple(d['rect'])
  if any(_inside(b,n['bbox'],.1) for n in nodes):continue
  if any(_inside(b,_union([[*tip,*tip],[*base,*base]]),4) for tip,base in heads):continue
  uninterpreted.append(list(b))
 return dict(nodes=nodes,edges=edges,unbound_inputs=unbound,unresolved_arrows=unresolved,uninterpreted_strokes=uninterpreted)

def _gcn_profile(ink,fields):
 graph=_vector_graph(ink);nodes=graph['nodes'];edges=graph['edges']
 if len(nodes)<4 or len(edges)!=len(nodes)-1:return None
 incoming={i:[e['source'] for e in edges if e['target']==i] for i in range(len(nodes))}
 aggregate=[i for i,src in incoming.items() if len(src)>=2];end=[i for i,src in incoming.items() if len(src)==1]
 if len(aggregate)!=1 or len(end)!=1:return None
 agg=aggregate[0];out=end[0]
 if incoming[out]!=[agg] or set(incoming[agg])!={i for i in range(len(nodes)) if i not in {agg,out}}:return None
 for i,node in enumerate(nodes):
  names=[_text(f['text']) for f in fields if _inside(f['bbox'],node['bbox'],1)]
  if not any(re.fullmatch(r'h\(l\+1\)',n) if i==out else re.fullmatch(r'h\(l\)',n) for n in names):return None
 transform=[f for f in fields if re.fullmatch(r'σ\(w[·⋅]?agg\)',_text(f['text']))]
 if len(transform)!=1 or not nodes[agg]['bbox'][2]<_center(transform[0]['bbox'])[0]<nodes[out]['bbox'][0]:return None
 alphas=[f for f in fields if re.match(r'α',_text(f['text']))]
 if len(alphas)!=len(incoming[agg]):return None
 return dict(kind='weighted_neighbor_aggregation_then_next_layer',graph=graph,transform=transform[0],weights=alphas)

def _runs(mask):
 """Centers of contiguous observed rule strokes."""
 positions=[i for i,x in enumerate(mask) if x];groups=[]
 for i in positions:
  if not groups or i>groups[-1][-1]+1:groups.append([i])
  else:groups[-1].append(i)
 return [round(sum(g)/len(g)) for g in groups]

def convolution_raster_layout(rgb):
 """Repeated actual grids, stable kernel ink, moving window/output ownership."""
 import cv2,numpy as np
 if rgb.ndim!=3 or rgb.shape[2]!=3:return None
 gray=cv2.cvtColor(rgb,cv2.COLOR_RGB2GRAY);height,width=gray.shape
 bw=(gray<150).astype(np.uint8)*255
 h=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((1,max(12,width//65)),np.uint8))
 v=cv2.morphologyEx(bw,cv2.MORPH_OPEN,np.ones((max(12,height//25),1),np.uint8))
 contours,_=cv2.findContours(h|v,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);grids=[]
 for contour in contours:
  x,y,w,hh=cv2.boundingRect(contour)
  if min(w,hh)<width*.03 or not .8<w/max(hh,1)<1.2:continue
  vertical=_runs(np.mean(v[y:y+hh,x:x+w]>0,axis=0)>.75);horizontal=_runs(np.mean(h[y:y+hh,x:x+w]>0,axis=1)>.75)
  if len(vertical)<3 or len(horizontal)!=len(vertical):continue
  if max(np.diff(vertical))/min(np.diff(vertical))>1.12 or max(np.diff(horizontal))/min(np.diff(horizontal))>1.12:continue
  grids.append(dict(bbox=[x,y,x+w,y+hh],vertical=[x+i for i in vertical],horizontal=[y+i for i in horizontal],cells=len(vertical)-1))
 if not 12<=len(grids)<=36 or len(grids)%3:return None
 grids.sort(key=lambda g:(round(g['bbox'][1]/max(g['bbox'][3]-g['bbox'][1],1)),g['bbox'][0]))
 bands=[]
 for g in sorted(grids,key=lambda g:(g['bbox'][1],g['bbox'][0])):
  if bands and abs(g['bbox'][1]-bands[-1][0]['bbox'][1])<height*.04:bands[-1].append(g)
  else:bands.append([g])
 triples=[]
 for band in bands:
  band.sort(key=lambda g:g['bbox'][0])
  if len(band)%3:return None
  triples.extend([band[k:k+3] for k in range(0,len(band),3)])
 kernels=[];stages=[]
 def cell(g,row,col):
  a,b=g['vertical'][col:col+2];c,d=g['horizontal'][row:row+2];m=max(2,round(min(b-a,d-c)*.18));return rgb[c+m:d-m,a+m:b-m]
 for source,kernel,output in triples:
  n,k,o=source['cells'],kernel['cells'],output['cells']
  if not n>k>=2 or o!=n-k+1 or len(triples)!=o*o:return None
  patches=[cell(kernel,r,c) for r in range(k) for c in range(k)];colors=[np.median(p.reshape(-1,3),axis=0) for p in patches]
  if any(np.max(np.abs(c-colors[0]))>5 for c in colors) or max(colors[0])-min(colors[0])<20:return None
  color=colors[0];mask=np.array([[np.max(np.abs(np.median(cell(source,r,c).reshape(-1,3),axis=0)-color))<6 for c in range(n)] for r in range(n)])
  selected=np.argwhere(mask)
  if len(selected)!=k*k:return None
  row,col=selected.min(0);expected=np.zeros((n,n),bool);expected[row:row+k,col:col+k]=True
  if not np.array_equal(mask,expected):return None
  hits=[(r,c) for r in range(o) for c in range(o) if np.max(np.abs(np.median(cell(output,r,c).reshape(-1,3),axis=0)-color))<6]
  if hits!=[(int(row),int(col))]:return None
  bits=[cv2.resize((cv2.cvtColor(p,cv2.COLOR_RGB2GRAY)<100).astype(np.uint8),(32,32),interpolation=cv2.INTER_NEAREST) for p in patches]
  kernels.append(bits)
  # The operation glyph is a circled cross. The output edge must actually
  # carry a rightward arrowhead, rather than merely sit beside a grid.
  gaps=[]
  for a,b in ((source,kernel),(kernel,output)):
   left,right=a['bbox'][2],b['bbox'][0];top=max(a['bbox'][1],b['bbox'][1]);bottom=min(a['bbox'][3],b['bbox'][3]);gaps.append(bw[top:bottom,left:right])
  cross_crop,arrow_crop=gaps
  cc,_=cv2.findContours(cross_crop,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
  circles=[c for c in cc if cv2.contourArea(c)>15 and .75<cv2.boundingRect(c)[2]/max(cv2.boundingRect(c)[3],1)<1.3 and 4*math.pi*cv2.contourArea(c)/max(cv2.arcLength(c,True)**2,1)>.55]
  if len(circles)!=1:return None
  cx,cy,cw,ch=cv2.boundingRect(circles[0]);inner=cross_crop[cy+round(ch*.2):cy+round(ch*.8),cx+round(cw*.2):cx+round(cw*.8)]
  lines=cv2.HoughLinesP(inner,1,np.pi/180,threshold=max(3,min(inner.shape)//3),minLineLength=max(3,min(inner.shape)*.4),maxLineGap=2)
  angles=[] if lines is None else [math.degrees(math.atan2(y2-y1,x2-x1)) for x1,y1,x2,y2 in lines.reshape(-1,4)]
  if not any(25<abs(a)<65 for a in angles) or not any(a>20 for a in angles) or not any(a< -20 for a in angles):return None
  ac,_=cv2.findContours(arrow_crop,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE);rightward=False
  for contour in ac:
   poly=cv2.approxPolyDP(contour,max(.7,cv2.arcLength(contour,True)*.02),True).reshape(-1,2)
   if not 3<=len(poly)<=8 or cv2.contourArea(contour)<5:continue
   tip=poly[poly[:,0].argmax()];back=np.delete(poly,poly[:,0].argmax(),axis=0)
   left=poly[poly[:,0]<=poly[:,0].min()+2]
   if tip[0]-max(back[:,0])>.5 and min(back[:,1])+2<tip[1]<max(back[:,1])-2 and max(abs(left[:,1]-tip[1]))<=2:rightward=True
  if not rightward:return None
  stages.append(dict(input_grid=source,kernel_grid=kernel,output_grid=output,window_origin=[int(row),int(col)],output_cell=list(hits[0]),operation='observed circled cross',output_direction='right'))
 if any(np.mean(np.abs(a.astype(float)-b.astype(float)))>.08 for old in kernels[1:] for a,b in zip(kernels[0],old)):return None
 if len({tuple(s['window_origin']) for s in stages})!=len(stages):return None
 return dict(kind='shared_kernel_sliding_multiply_sum',raster_shape=list(rgb.shape),stages=stages)

def _color_shapes(rgb):
 import cv2,numpy as np
 colored=((rgb.max(2).astype(int)-rgb.min(2).astype(int)>30)&(rgb.mean(2)>90)).astype(np.uint8)
 count,labels,stats,centers=cv2.connectedComponentsWithStats(colored,8);result=[]
 for k,(x,y,w,h,size) in enumerate(stats[1:],1):
  if size<40 or min(w,h)<4:continue
  points,_=cv2.findContours((labels==k).astype(np.uint8),cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
  if len(points)!=1:continue
  poly=cv2.approxPolyDP(points[0],max(.7,cv2.arcLength(points[0],True)*.018),True).reshape(-1,2)
  color=np.median(rgb[labels==k],axis=0)
  if size>rgb.shape[0]*rgb.shape[1]*.02:
   # A thin dimension stroke can touch a filled matrix. Its other color is
   # not part of the matrix's physical taper or bottleneck boundary.
   same=(np.max(np.abs(rgb[y:y+h,x:x+w].astype(float)-color),axis=2)<8).astype(np.uint8)
   clean,_=cv2.findContours(same,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
   if clean:
    contour=max(clean,key=cv2.contourArea);contour=contour+np.array([[[x,y]]]);xx,yy,ww,hh=cv2.boundingRect(contour)
    if cv2.contourArea(contour)>size*.7:
     x,y,w,h=xx,yy,ww,hh;poly=cv2.approxPolyDP(contour,max(.7,cv2.arcLength(contour,True)*.018),True).reshape(-1,2)
  result.append(dict(bbox=[int(x),int(y),int(x+w),int(y+h)],area=int(size),color=color.tolist(),polygon=poly.tolist()))
 return result

def _arrow_seven(poly):
 if len(poly)!=7:return None
 import numpy as np
 a=np.array(poly,float);cross=[]
 for i in range(7):
  u=a[i]-a[i-1];v=a[(i+1)%7]-a[i];cross.append(u[0]*v[1]-u[1]*v[0])
 positive=[i for i,v in enumerate(cross) if v>1];negative=[i for i,v in enumerate(cross) if v< -1]
 concave=positive if len(positive)==2 else negative if len(negative)==2 else []
 if len(concave)!=2:return None
 for start,end in ((concave[0],concave[1]),(concave[1],concave[0])):
  if (end-start)%7==4:
   return a[(start+2)%7].tolist(),((a[(end+1)%7]+a[(end+2)%7])/2).tolist()
 return None

def lora_raster_layout(rgb):
 """Original colored base/bottleneck branches, four arrowheads and sum glyph."""
 shapes=_color_shapes(rgb);height,width=rgb.shape[:2]
 large=[s for s in shapes if s['area']>height*width*.012];bars=[s for s in large if (s['bbox'][2]-s['bbox'][0])>4*(s['bbox'][3]-s['bbox'][1])]
 matrices=[s for s in large if s not in bars]
 if len(bars)!=2 or len(matrices)!=3:return None
 bars.sort(key=lambda s:s['bbox'][1]);matrices.sort(key=lambda s:_center(s['bbox'])[0]);base=matrices[0];side=sorted(matrices[1:],key=lambda s:s['bbox'][1]);upper,lower=side
 if not base['bbox'][2]<min(s['bbox'][0] for s in side) or not bars[0]['bbox'][3]<min(s['bbox'][1] for s in matrices) or not max(s['bbox'][3] for s in matrices)<bars[1]['bbox'][1]:return None
 if abs(_center(upper['bbox'])[0]-_center(lower['bbox'])[0])>width*.03:return None
 def taper(s):
  p=s['polygon']
  if len(p)!=4:return None
  top=sorted(p,key=lambda p:p[1])[:2];bottom=sorted(p,key=lambda p:p[1])[2:]
  return abs(top[0][0]-top[1][0]),abs(bottom[0][0]-bottom[1][0])
 u,l=taper(upper),taper(lower)
 if u is None or l is None or not u[0]>u[1]*1.3 or not l[1]>l[0]*1.3 or abs(u[1]-l[0])>width*.03:return None
 arrows=[];sum_sign=[]
 for s in shapes:
  if s in large:continue
  tip=_arrow_seven(s['polygon'])
  if tip and tip[0][1]<tip[1][1]-5:arrows.append(dict(bbox=s['bbox'],tip=tip[0],tail=tip[1]))
  b=s['bbox'];w,h=b[2]-b[0],b[3]-b[1]
  if .85<w/max(h,1)<1.15 and len(s['polygon'])>=10 and bars[0]['bbox'][3]<b[1]<upper['bbox'][1] and base['bbox'][2]<_center(b)[0]<upper['bbox'][0]:sum_sign.append(s)
 if len(arrows)!=4 or len(sum_sign)!=1:return None
 above=[a for a in arrows if a['bbox'][3]<min(s['bbox'][1] for s in matrices)+5];below=[a for a in arrows if a['bbox'][1]>max(s['bbox'][3] for s in matrices)-5]
 if len(above)!=2 or len(below)!=2:return None
 def near_face(point,shape,face):
  b=shape['bbox'];gap=(b[1]-point[1]) if face=='top' else (point[1]-b[3])
  return b[0]-width*.04<=point[0]<=b[2]+width*.04 and -2<=gap<=height*.08
 upper_owners=[];lower_owners=[]
 for arrow in above:
  sources=[name for name,shape in (('base',base),('zero_output_projection',upper)) if near_face(arrow['tail'],shape,'top')]
  if len(sources)!=1 or not near_face(arrow['tip'],bars[0],'bottom'):return None
  upper_owners.append(sources[0])
 for arrow in below:
  targets=[name for name,shape in (('base',base),('random_input_projection',lower)) if near_face(arrow['tip'],shape,'bottom')]
  if len(targets)!=1 or not near_face(arrow['tail'],bars[1],'top'):return None
  lower_owners.append(targets[0])
 if set(upper_owners)!={'base','zero_output_projection'} or set(lower_owners)!={'base','random_input_projection'}:return None
 return dict(kind='frozen_base_plus_low_rank_bypass',raster_shape=list(rgb.shape),base=base,zero_output_projection=upper,random_input_projection=lower,input_bar=bars[1],output_bar=bars[0],arrows=arrows,sum_glyph=sum_sign[0],upper_arrow_sources=upper_owners,lower_arrow_targets=lower_owners)

def _pdf_box(ink,box):
 x,y=ink['raster_origin'];scale=ink['render_scale'];return [(x+box[0])/scale,(y+box[1])/scale,(x+box[2])/scale,(y+box[3])/scale]

def _projection_blocks(ink,fields):
 blocks=[]
 for name in ('linear','bottleneckmlp','softmax'):
  native=[f for f in fields if f.get('source')=='native' and _text(f['text'])==name]
  if len(native)!=1:return []
  field=native[0];c=_center(field['bbox']);parts=[]
  for d in ink['drawings']:
   b=tuple(d['rect']);fill=d.get('fill')
   if fill is None or max(fill)-min(fill)<.02 or b[2]-b[0]<field['bbox'][2]-field['bbox'][0] or b[3]-b[1]<8:continue
   if b[0]<=c[0]<=b[2] and b[1]-3<=c[1]<=b[3]+3:parts.append(b)
  if not parts:return []
  box=_union(parts)
  if not _inside(field['bbox'],box,1):return []
  blocks.append(dict(kind=name,bbox=box,printed_field=field))
 outputs=[f for f in fields if f.get('source')=='native' and _text(f['text'])=='output']
 if len(outputs)!=2:return []
 blocks.extend(dict(kind='output',bbox=f['bbox'],printed_field=f) for f in outputs)
 return blocks

def _glyph_signature(d):
 """Compare painted glyph outline, independent of translation on the page."""
 box=tuple(d['rect']);items=[]
 for item in d['items']:
  if item[0] not in {'c','l'}:return None
  points=[[round(p[0]-box[0],2),round(p[1]-box[1],2)] for p in item[1:]]
  items.append([item[0],*points])
 if d.get('type') not in {'fs','f'} or len(items)<7 or box[2]-box[0]>15:return None
 return repr(items)

def _closed_label_boundaries(ink,profile,native):
 """Original painted component/path boundaries, independent of OCR words."""
 import cv2,numpy as np
 answer=[]
 if profile and profile['kind']=='frozen_base_plus_low_rank_bypass':
  for role in ('zero_output_projection','random_input_projection'):
   x,y,xx,yy=profile[role]['bbox'];gray=cv2.cvtColor(ink['rgb'][y:yy,x:xx],cv2.COLOR_RGB2GRAY)
   count,labels,stats,centers=cv2.connectedComponentsWithStats((gray<128).astype(np.uint8),8)
   parts=[[int(x+a),int(y+b),int(x+a+w),int(y+b+h)] for a,b,w,h,size in stats[1:] if size>=2]
   if not 3<=len(parts)<=16:continue
   box=_union(parts);height=box[3]-box[1]
   if not 8<=height<=35 or box[2]-box[0]>10*height:continue
   # A line of isolated black glyphs inside the independently observed
   # colored projection, rather than its boundary or an outside paragraph.
   if not all(_inside(p,[x+2,y+2,xx-2,yy-2]) for p in parts):continue
   answer.append(dict(kind='black_components_in_closed_projection',bbox=box,components=parts,physical_role=role))
 blocks=_projection_blocks(ink,native)
 if blocks:
  for block in blocks:
   if block['kind'] not in {'linear','bottleneckmlp'}:continue
   b=block['bbox']
   ds=[d for d in ink['drawings'] if _glyph_signature(d) and b[0]<d['rect'].x0<d['rect'].x1<b[2] and b[1]-30<d['rect'].y0<d['rect'].y1<b[1]]
   if len(ds)!=3:continue
   for d in ds:
    box=[v*ink['render_scale']-ink['raster_origin'][i%2] for i,v in enumerate(d['rect'])]
    answer.append(dict(kind='closed_original_vector_glyph',bbox=box,vector_signature=_glyph_signature(d),physical_role=block['kind']))
  for node in _vector_graph(ink)['nodes']:
   ds=[d for d in ink['drawings'] if _inside(tuple(d['rect']),node['bbox'],1) and _glyph_signature(d)]
   if len(ds)!=1:continue
   d=ds[0];box=[v*ink['render_scale']-ink['raster_origin'][i%2] for i,v in enumerate(d['rect'])]
   answer.append(dict(kind='closed_original_vector_glyph',bbox=box,vector_signature=_glyph_signature(d),physical_role='kernel_transform'))
 return answer

def closed_ink_recipe():
 """Current model, original-pixel boundary and recognition recipe identity."""
 from pathlib import Path
 from hashlib import sha256
 from .usage_graphic_ocr import _ocr_signature,_json
 return sha256(_json(dict(helper=sha256(Path(__file__).read_bytes()).hexdigest(),reader=_ocr_signature(),
   procedure='original-RGB-3x-closed-boundary-margin6-rec-only',min_recognition=.98))).hexdigest()

def validate_closed_ink_record(record,pdf_sha=None,recipe=None):
 """Pure data validator for independently seeded closed-ink observations.

 Matching original painted pixels and the boundary are checked again when
 usage regenerates the context. This function never decides figure usage.
 """
 from hashlib import sha256
 from .usage_graphic_ocr import _json,_box
 try:
  if not isinstance(record,dict) or set(record)!={'format','context','observation','observation_sha'} or record['format']!='closed-diagram-ink-v1':return False
  c=record['context'];o=record['observation']
  if set(c)!={'pdf_sha','page_number','region_bbox','bbox','boundary','pixel_sha','recipe','render_scale','raster_origin'} or set(o)!={'text','confidence'}:return False
  if not all(isinstance(c[k],str) and re.fullmatch(r'[0-9a-f]{64}',c[k]) for k in ('pdf_sha','pixel_sha','recipe')):return False
  if pdf_sha is not None and c['pdf_sha']!=pdf_sha:return False
  if c['recipe']!=(closed_ink_recipe() if recipe is None else recipe):return False
  if not isinstance(c['page_number'],int) or isinstance(c['page_number'],bool) or c['page_number']<1 or c['render_scale']!=3:return False
  b=_box(c['bbox']);area=_box(c['region_bbox']);boundary=c['boundary']
  if b is None or area is None or not _inside(b,area,.01) or not isinstance(boundary,dict):return False
  p=_box(boundary['bbox']);origin=c['raster_origin']
  if p is None or not isinstance(origin,list) or len(origin)!=2 or not all(isinstance(v,int) for v in origin):return False
  expected=[(origin[i%2]+v)/3 for i,v in enumerate(p)]
  if any(abs(a-v)>.001 for a,v in zip(b,expected)):return False
  if boundary['kind']=='closed_original_vector_glyph':
   if set(boundary)!={'kind','bbox','vector_signature','physical_role'} or boundary['physical_role'] not in {'linear','bottleneckmlp','kernel_transform'} or not isinstance(boundary['vector_signature'],str):return False
  elif boundary['kind']=='black_components_in_closed_projection':
   if set(boundary)!={'kind','bbox','components','physical_role'} or boundary['physical_role'] not in {'zero_output_projection','random_input_projection'}:return False
   parts=boundary['components']
   if not isinstance(parts,list) or not 3<=len(parts)<=16 or any(_box(part) is None or not _inside(part,p) for part in parts) or _union(parts)!=list(p):return False
  else:return False
  if not isinstance(o['text'],str) or any(ord(ch)<32 and not ch.isspace() for ch in o['text']):return False
  if not isinstance(o['confidence'],(int,float)) or isinstance(o['confidence'],bool) or not math.isfinite(o['confidence']) or not 0<=o['confidence']<=1:return False
  return record['observation_sha']==sha256(_json(o)).hexdigest()
 except (KeyError,TypeError,ValueError,OverflowError):return False

def _closed_ink_fields(ink,profile,native):
 """Recognize known physical ink boundaries without invented detector scores."""
 import cv2,json,os
 from pathlib import Path
 from hashlib import sha256
 from .usage_graphic_ocr import _json
 from .local_ocr import _engine
 from rapidocr.ch_ppocr_rec import TextRecInput
 recipe=closed_ink_recipe()
 fields=[]
 for boundary in _closed_label_boundaries(ink,profile,native):
  x,y,xx,yy=[round(v) for v in boundary['bbox']];rgb=ink['rgb'];margin=6
  crop=rgb[max(0,y-margin):min(len(rgb),yy+margin),max(0,x-margin):min(rgb.shape[1],xx+margin)].copy()
  if not crop.size:continue
  context=dict(pdf_sha=ink['pdf_sha'],page_number=ink['page_number'],region_bbox=ink['bbox'],
    bbox=_pdf_box(ink,boundary['bbox']),boundary=boundary,pixel_sha=sha256(crop.tobytes()).hexdigest(),recipe=recipe,
    render_scale=ink['render_scale'],raster_origin=ink['raster_origin'])
  identity=sha256(_json(context)).hexdigest();record=None;root=os.environ.get('MINERU_USAGE_DIAGRAM_FACTS_DIR')
  if not root and os.environ.get('MINERU_USAGE_OCR_CACHE_DIR'):root=str(Path(os.environ['MINERU_USAGE_OCR_CACHE_DIR'])/'diagram_closed_ink')
  path=Path(root)/('usage-diagram-closed-'+identity+'.json') if root else None
  if path:
   try:
    loaded=json.loads(path.read_text(encoding='utf8'))
    if loaded.get('context')==context and validate_closed_ink_record(loaded,ink['pdf_sha'],recipe):record=loaded['observation']
   except (OSError,ValueError,TypeError):pass
  if record is None:
   try:
    result=_engine().text_rec(TextRecInput(img=[cv2.cvtColor(crop,cv2.COLOR_RGB2BGR)]))
    record=dict(text=result.txts[0],confidence=float(result.scores[0])) if len(result.txts)==1 and len(result.scores)==1 else dict(text='',confidence=0.)
   except (ImportError,ValueError,RuntimeError,IndexError,AttributeError):continue
   if path:
    try:
     path.parent.mkdir(parents=True,exist_ok=True)
     payload=_json(dict(format='closed-diagram-ink-v1',context=context,observation=record,observation_sha=sha256(_json(record)).hexdigest()))
     # The context hash makes each observation immutable and source-bound.
     with path.open('xb') as target:target.write(payload)
    except OSError:pass
  confidence=record.get('confidence');text=record.get('text')
  if not isinstance(confidence,(int,float)) or not .98<=confidence<=1 or not isinstance(text,str) or not text.strip():continue
  fields.append(dict(text=text,bbox=context['bbox'],page_number=ink['page_number'],source='original_closed_ink_recognition',
    confidence=confidence,pdf_sha=ink['pdf_sha'],boundary_identity=identity,closed_boundary=boundary,pixel_sha=context['pixel_sha'],recipe=recipe))
 return fields

def _attention_profile(ink,fields):
 blocks=_projection_blocks(ink,fields)
 if not blocks:return None
 graph=_vector_graph(ink,blocks);nodes=graph['nodes'];edges=graph['edges'];pos={n['kind']:i for i,n in enumerate(nodes) if n['kind']!='circle'}
 if graph['unresolved_arrows'] or graph['uninterpreted_strokes']:return None
 linear,mlp,soft=pos['linear'],pos['bottleneckmlp'],pos['softmax']
 if not _center(nodes[linear]['bbox'])[0]<_center(nodes[mlp]['bbox'])[0]:return None
 split=(_center(nodes[linear]['bbox'])[0]+_center(nodes[mlp]['bbox'])[0])/2
 role_fields={};matched=[]
 for role in ('q','k','v'):
  observations=[f for f in fields if _text(f['text'])==role and _center(f['bbox'])[0]<split and nodes[linear]['bbox'][1]-30<=_center(f['bbox'])[1]<=nodes[linear]['bbox'][1]]
  if not observations:return None
  seed=max(observations,key=lambda f:f.get('confidence',1))
  glyphs=[d for d in ink['drawings'] if _inside(tuple(d['rect']),seed['bbox'],1) and _glyph_signature(d)]
  if len(glyphs)!=1:return None
  signature=_glyph_signature(glyphs[0]);same=[d for d in ink['drawings'] if _glyph_signature(d)==signature and nodes[mlp]['bbox'][0]<d['rect'].x0<nodes[mlp]['bbox'][2] and nodes[mlp]['bbox'][1]-30<d['rect'].y0<nodes[mlp]['bbox'][1]]
  if len(same)!=1:return None
  role_fields[role]=(tuple(glyphs[0]['rect']),tuple(same[0]['rect']))
  matched.append(dict(role=role,observed_field=seed,original_left_glyph_bbox=list(glyphs[0]['rect']),original_right_glyph_bbox=list(same[0]['rect']),evidence='High-confidence actual left optical field and identical translated original vector outline at the corresponding right input.'))
 def direct(a,b):return any(e['source']==a and e['target']==b for e in edges)
 def role_target(projection,role,panel):
  center=_center(role_fields[role][panel])[0]
  options=[e for e in edges if e['source']==projection and abs(e['tail'][0]-center)<20]
  return options[0]['target'] if len(options)==1 else None
 lq,lk,lv=[role_target(linear,r,0) for r in ('q','k','v')];rq,rk,rv=[role_target(mlp,r,1) for r in ('q','k','v')]
 if any(v is None for v in (lq,lk,lv,rq,rk,rv)) or lq!=lk or lq==lv or len({rq,rk,rv})!=3:return None
 circles=[i for i,n in enumerate(nodes) if n['kind']=='circle']
 if len(circles)!=6:return None
 def multiplication(i):
  b=nodes[i]['bbox'];lines=[d for d in ink['drawings'] if d['type']=='s' and len(d['items'])==1 and d['items'][0][0]=='l' and _inside(tuple(d['rect']),b,.1)]
  slopes=[(tuple(d['items'][0][1]),tuple(d['items'][0][2])) for d in lines]
  return any((q[0]-p[0])*(q[1]-p[1])>20 for p,q in slopes) and any((q[0]-p[0])*(q[1]-p[1])< -20 for p,q in slopes)
 if not all(multiplication(i) for i in (lq,lv,rv)) or multiplication(rq) or multiplication(rk):return None
 right_top=[i for i in circles if i not in {lq,lv,rq,rk,rv}]
 if len(right_top)!=1:return None
 top=right_top[0]
 if not multiplication(top) or not all(direct(a,b) for a,b in ((lq,soft),(soft,lv),(rq,top),(rk,rv),(rv,top))):return None
 # The two feature transformations carry identical original operator glyphs;
 # their alphabet is not guessed from the explanatory equation.
 operators=[]
 for i in (rq,rk):
  ds=[d for d in ink['drawings'] if _inside(tuple(d['rect']),nodes[i]['bbox'],1) and _glyph_signature(d)]
  if len(ds)!=1:return None
  if not any(_text(f['text']) in {'φ','ϕ'} and _inside(f['bbox'],nodes[i]['bbox'],1) for f in fields):return None
  operators.append(ds[0])
 if _glyph_signature(operators[0])!=_glyph_signature(operators[1]):return None
 out=[i for i,n in enumerate(nodes) if n['kind']=='output']
 if len(out)!=2 or not any(direct(lv,i) for i in out) or not any(direct(top,i) for i in out):return None
 from collections import Counter
 left_out,right_out=sorted(out,key=lambda i:_center(nodes[i]['bbox'])[0])
 expected=[(linear,lq),(linear,lk),(linear,lv),(lq,soft),(soft,lv),(lv,left_out),(mlp,rq),(mlp,rk),(mlp,rv),(rq,top),(rk,rv),(rv,top),(top,right_out)]
 if Counter((e['source'],e['target']) for e in edges)!=Counter(expected):return None
 if len(graph['unbound_inputs'])!=6:return None
 for projection in (linear,mlp):
  inputs=[e for e in graph['unbound_inputs'] if e['target']==projection and e['tail'][1]>nodes[projection]['bbox'][3]+10 and e['tip'][1]<e['tail'][1]-10]
  if len(inputs)!=3 or len({round(e['tail'][0]) for e in inputs})!=3:return None
 return dict(kind='projected_attention_association',graph=graph,printed_roles=matched,nonlinear_operator_bboxes=[list(d['rect']) for d in operators],
             left_relations=['first two projected roles multiply','SoftMax','third role multiply','Output'],right_relations=['first/second roles undergo matching feature transform','second and third roles multiply','first role then multiplies that result','Output'])

def _observation_regions(area,ink,profile,native):
 answer=[dict(area)]
 if profile and profile['kind']=='frozen_base_plus_low_rank_bypass':
  for name in ('base','zero_output_projection','random_input_projection'):
   b=_pdf_box(ink,profile[name]['bbox']);b=[max(area['bbox'][0],b[0]-3),max(area['bbox'][1],b[1]-3),min(area['bbox'][2],b[2]+3),min(area['bbox'][3],b[3]+3)]
   answer.append({**area,'bbox':b})
 if _projection_blocks(ink,native):
  split=(area['bbox'][0]+area['bbox'][2])/2
  answer.extend([{**area,'bbox':[area['bbox'][0],area['bbox'][1],split,area['bbox'][3]]},{**area,'bbox':[split,area['bbox'][1],area['bbox'][2],area['bbox'][3]]}])
 return answer

def _validated_fields(document,areas,fields,ink):
 from hashlib import sha256
 from .usage_graphic_ocr import _json,_valid_facts
 native={(r.page_number,tuple(r.bbox),r.text) for p in document.pages for r in p.lines if r.source=='native'}
 contexts=[]
 for area in areas:
  physical=dict(pdf_sha=ink['pdf_sha'],page_number=area['page_number'],bbox=[float(v) for v in area['bbox']]);contexts.append({**physical,'region_identity':sha256(_json(physical)).hexdigest()})
 return [f for f in fields if (f.get('source')=='native' and (f['page_number'],tuple(f['bbox']),f['text']) in native) or any(_valid_facts([f],c) for c in contexts)]

def _lora_printed_roles(ink,profile,fields):
 selected={}
 for role,pattern in (('base',r'预训练权重|pretrained(?:weights?)?'),('zero_output_projection',r'b=0'),('random_input_projection',r'a=n\(0,σ(?:2)?\)')):
  box=_pdf_box(ink,profile[role]['bbox']);hits=[f for f in fields if _inside(f['bbox'],box,3) and re.fullmatch(pattern,_text(f['text']))]
  if not hits:return False
  selected[role]=max(hits,key=lambda f:f.get('confidence',1))
 profile['printed_roles']=selected;return True

def _denied_or_foreign(value,target,title):
 from .numbering import normalize_label
 s=unicodedata.normalize('NFKC',normalize_text(value));compact=_text(s)
 refs=re.findall(r'(?:图|figures?|fig\.?)\s*([a-z]?\d+(?:[.\-–]\d+)*)',s,re.I)
 if any(normalize_label(n)!=target.number for n in refs):return True
 if re.search(r'(?:未|不|没有|无需)(?:采用|使用|执行|实现|说明|解释|讨论)(?:上述|该|此|本|所示)?(?:机制|图|方法|运算|传播|流程)|(?:另一|其他|另一个).{0,20}(?:模型|方法|网络|架构)|(?:文献|外部论文|另一篇论文).{0,20}(?:图|流程)',compact,re.I):return True
 if re.search(r'\b(?:not|never|without).{0,30}\b(?:use|using|used|employ|perform|implement|explain|discuss)|\b(?:another|other)\s+(?:model|method|network|architecture)',s,re.I):return True
 owners=set(re.findall(r'(?<![a-z])[a-z][a-z0-9_-]{2,}(?![a-z])',_text(title)))
 # Credit requires the actual explanatory operation's subject. Possessives,
 # action adverbs and passive "performed by" frames do not change its owner.
 actor=r'([A-Za-z][A-Za-z0-9_-]+)'
 entity=r'(?:model|method|algorithm|network|architecture)'
 operation=r'(?:uses?|employs?|performs?|implements?|executes?|maps?|constructs?)'
 active=r'\b'+actor+r"(?:['’]s)?\s+"+entity+r'\s+(?:[A-Za-z]+ly\s+){0,2}'+operation+r'\b'
 passive=r'\b(?:used|employed|performed|implemented|executed|mapped|constructed)\s+by\s+(?:the\s+)?'+actor+r'(?:[\u0027’]s)?\s+'+entity+r'\b'
 for name in re.findall(active,s,re.I)+re.findall(passive,s,re.I):
  if _text(name) not in owners and _text(name) not in {'this','that','the','our','same','proposed'}:return True
 for name in re.findall(r'([A-Za-z][A-Za-z0-9_-]{1,}|[\u4e00-\u9fff]{2,12})(?:模型|方法|算法|网络|架构)(?:采用|执行|使用|实现|映射|构造)',compact):
  name=re.sub(r'^(?:本文|本章|本节|我们)?(?:采用|使用)?','',name)
  if name in {'该','本','此','上述','前述','图卷积','卷积','二维卷积','低秩线性注意力'}:continue
  if name and name not in owners and name not in compact[:compact.find(name)] and name not in _text(title):return True
 return False

def _body_requirements(kind,passages,target,title):
 patterns={
  'shared_kernel_sliding_multiply_sum':(r'卷积核.{0,80}(?:像素逐一相乘|像素相乘).{0,20}求和',r'同一卷积核.{0,90}权重参数.{0,30}保持不变',r'水平和垂直方向.{0,20}滑动',r'遍历.{0,20}所有有效区域.{0,30}完整.{0,10}输出特征图'),
  'weighted_neighbor_aggregation_then_next_layer':(r'(?:单层特征更新|节点.{0,20}更新)',r'可学习的线性变换矩阵',r'非线性激活函数',r'(?:邻域.{0,20}聚合|邻域特征.{0,20}加权平均)',r'自连接',r'对称归一化'),
  'frozen_base_plus_low_rank_bypass':(r'lora',r'输入投影矩阵.{0,10}随机初始化',r'输出投影矩阵.{0,15}初始化为.{0,100}全零',r'全程不参与梯度更新',r'只有a.{0,12}参数.{0,15}更新',r'插入a和b',r'旁路分支',r'不会改变主干网络的输出结果',r'h=w0x\+a[⋅·]?b[⋅·]?x'),
  'projected_attention_association':(r'低秩线性注意力',r'(?:两层|两全).{0,15}(?:前馈网络|ffn).{0,15}qkv.{0,10}映射',r'而非使用单层线性映射',r'代替softmax',r'φ\(x\)=elu\(x\)\+1',r'v.{0,15}φ\(k.{0,15}φ\(q\)'),
 }[kind]
 selected=[]
 for pattern in patterns:
  candidates=[(rows,value) for rows,value in passages if not _denied_or_foreign(value,target,title) and re.search(pattern,_text(value),re.I)]
  if not candidates:return []
  rows,value=min(candidates,key=lambda pair:sum(len(r.text) for r in pair[0]));selected.extend(rows)
 return list({(r.page_number,r.bbox,r.text):r for r in selected}.values())

def _original_body_veto(context,rows,target,title):
 """Inspect ink inside/next to selected prose, including small continuations."""
 areas=[a for aa in context['regions'].values() for a in aa];captions=context['caption_keys']
 identity=usage_scope_identity(context['usage_scopes'],target)
 for selected in rows:
  size=selected.font_size or 12.;native=[]
  for page in context['_document'].pages:
   if page.number!=selected.page_number:continue
   for row in page.lines:
    if row.source!='native' or (row.page_number,row.bbox) in captions or row.role in {'header','footer','toc','caption','reference'}:continue
    if usage_scope_identity(context['usage_scopes'],row)!=identity:continue
    if any(a['page_number']==row.page_number and _inside(row.bbox,a['bbox'],1) for a in areas):continue
    a=selected.bbox;b=row.bbox;overlap=min(a[2],b[2])-max(a[0],b[0]);center=(b[1]+b[3])/2
    if overlap<min(a[2]-a[0],b[2]-b[0])*.5 or not a[1]-size<=center<=a[3]+size:continue
    native.append(row)
  native.sort(key=lambda r:(r.bbox[1],r.bbox[0]))
  if any(_denied_or_foreign(r.text,target,title) for r in native) or _denied_or_foreign(' '.join(r.text for r in native),target,title):return True
 return False

def diagram_relation_proposals(context,groups,nearby,fields=None):
 """Complete actual topology plus independent local mechanism, never a gate."""
 from .usage_figure_relations import _near_passages
 from .usage_scope import is_body_usage_scope
 answer=[]
 for ordinal,areas in context['regions'].items():
  if len(areas)!=1 or not diagram_title_candidate(areas[0]['title']):continue
  if ordinal>=len(groups) or not groups[ordinal] or not is_body_usage_scope(context['usage_scopes'],groups[ordinal][0]):continue
  area=areas[0];ink=context.get('diagram_ink',{}).get(ordinal)
  if ink is None:continue
  title=area['title'];offered=(fields or context.get('native_fields',{})).get(ordinal,[])
  native=diagram_native_fields(type('_SourceView',(),{'document':context['_document']})(),{ordinal:areas}).get(ordinal,[])
  physical=lora_raster_layout(ink['rgb']) if re.search(r'LoRA',title,re.I) else None
  observations=_observation_regions(area,ink,physical,native)
  available=_validated_fields(context['_document'],observations,offered,ink)
  closed=_closed_ink_fields(ink,physical,native)
  # Independently generated optical facts remain in their own schema. A
  # caller cannot credit fabricated labels, scores, PDF or model identities.
  available.extend(f for f in offered if f in closed)
  profile=None
  if re.search(r'卷积.{0,10}(?:运算|操作)',title):profile=convolution_raster_layout(ink['rgb'])
  elif re.search(r'GCN|图卷积',title,re.I):profile=_gcn_profile(ink,available)
  elif re.search(r'LoRA',title,re.I):
   profile=lora_raster_layout(ink['rgb'])
   if profile and not _lora_printed_roles(ink,profile,available):profile=None
  else:profile=_attention_profile(ink,available)
  if profile is None:continue
  # Public callers cannot borrow caption fields, distant chapters or another
  # document epoch by returning a purported nearby paragraph.
  allowed={(r.page_number,r.bbox,r.text) for rr,value in _near_passages(context,groups,ordinal,2) for r in rr}
  passages=[(rr,value) for rr,value in nearby(ordinal) if rr and _text(value)==_text(' '.join(r.text for r in rr)) and
     all(r.source=='native' and (r.page_number,r.bbox,r.text) in allowed and
         usage_scope_identity(context['usage_scopes'],r)==usage_scope_identity(context['usage_scopes'],groups[ordinal][0]) for r in rr)]
  rows=_body_requirements(profile['kind'],passages,groups[ordinal][0],title)
  if rows and not _original_body_veto(context,rows,groups[ordinal][0],title):answer.append((ordinal,profile['kind'],rows,{**profile,'pdf_sha':ink['pdf_sha'],'page_number':ink['page_number'],'bbox':ink['bbox']}))
 return answer

def diagram_usage_evidence(index,groups,ordinals=None):
 """Independent rule-15 branch; never alter an index or inherited consumers."""
 from .usage_figure_evidence import prepare_figure_usage,_body_passages,figure_graphic_regions,_full_title
 from .usage_figure_relations import _near_passages,_continuation_passages
 wanted=set(range(len(groups))) if ordinals is None else set(ordinals)
 pages={p.number:p for p in index.document.pages}
 if not any(i in wanted and group and group[0].line.page_number in pages and diagram_title_candidate(_full_title(group,pages[group[0].line.page_number],'figure')[0]) for i,group in enumerate(groups)):return {}
 recovered=diagram_graphic_regions(index,groups,figure_graphic_regions(index,groups))
 if not wanted.intersection(recovered):return {}
 context=prepare_figure_usage(index,groups)
 # All candidates remain competitors. Only the caller's pending set can get
 # credit; no recovered geometry enters any inherited evidence branch.
 context=dict(context);context['regions']={**context['regions'],**recovered}
 context['body_passages']=_body_passages(index,context['regions'],context['caption_keys'],context['usage_scopes'])
 context['native_fields']=diagram_native_fields(index,recovered)
 context['diagram_ink']={i:_original_ink(index.document,areas[0]) for i,areas in recovered.items()}
 from .usage_graphic_ocr import graphic_ocr_fields
 observations={};combined={i:list(v) for i,v in context['native_fields'].items()}
 for i,areas in recovered.items():
  ink=context['diagram_ink'][i]
  if ink is None:continue
  title=areas[0]['title'];native=combined.get(i,[])
  if re.search(r'LoRA|注意力.{0,20}对比|attention.{0,20}comparison',title,re.I):
   profile=lora_raster_layout(ink['rgb']) if re.search(r'LoRA',title,re.I) else None
   observations[i]=_observation_regions(areas[0],ink,profile,native)
 if observations:
  optical=graphic_ocr_fields(index,observations)
  for i,fields in optical.items():combined.setdefault(i,[]).extend(_validated_fields(index.document,observations[i],fields,context['diagram_ink'][i]))
 for i,areas in recovered.items():
  ink=context['diagram_ink'][i]
  if ink is not None:
   profile=lora_raster_layout(ink['rgb']) if re.search(r'LoRA',areas[0]['title'],re.I) else None
   combined.setdefault(i,[]).extend(_closed_ink_fields(ink,profile,context['native_fields'].get(i,[])))
 continuations=_continuation_passages(context)
 proposals=diagram_relation_proposals(context,groups,lambda i:_near_passages(context,groups,i,2,continuations),combined)
 answer={}
 for ordinal,kind,rows,physical in proposals:
  ink={(r.page_number,r.bbox,r.text) for r in rows}
  if ordinal not in wanted or any(other!=ordinal and other_kind==kind and ink.intersection((r.page_number,r.bbox,r.text) for r in rr) for other,other_kind,rr,pp in proposals):continue
  answer[ordinal]=dict(evidence_kind=kind,group=[dict(number=l.number,page_number=l.line.page_number,bbox=list(l.line.bbox),text=l.line.text) for l in groups[ordinal]],
    full_title=recovered[ordinal][0]['title'],graphic_regions=recovered[ordinal],graphic_fields=combined.get(ordinal,[]),optical_observation_regions=observations.get(ordinal,[]),
    body_evidence=[dict(page_number=r.page_number,bbox=list(r.bbox),text=r.text,source=r.source) for r in rows],physical_topology=physical,
    uniqueness_reason='Complete original directed topology and independent same-epoch/chapter mechanism; all physical candidates compete for shared body ink.')
 return answer
