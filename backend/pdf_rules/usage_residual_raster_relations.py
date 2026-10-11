"""Observe paired photographs/response maps and bind their body explanation.

This recognizes spatial correspondence and a nontrivial response, not the
unobserved reconstruction itself or semantic labels invented for the pixels.
"""
import re
from .usage_text_cache import normalize_text
from .usage_roadmap_relations import _owned_passages,_denied_operation


def residual_response_title(title):
    return bool(re.search(r'图像.{0,20}(?:特征增强|重构|残差|差值)|(?:feature|image).{0,20}(?:reconstruction|residual)',title,re.I))


def _contrast_rows(passages,page):
    target=[];background=[]
    for rows,value in passages:
        if not rows or any(r.page_number!=page for r in rows) or _denied_operation(value):continue
        text=re.sub(r'\s+','',normalize_text(value))
        # A shared list of reconstruction terms does not override an explicit
        # statement that the description belongs to another figure or model.
        if re.search(r'(?:不|未)(?:对应|属于)(?:本|此)(?:文)?(?:图像?|模型|方法|实验)|'
                     r'(?:属于|来自).{0,20}(?:另一|其他|别的).{0,10}(?:图像?|模型|实验)|'
                     r'(?:不|未|没有|无需|不必)(?:进行|执行)?重构',text):continue
        if (re.search(r'目标区域.{0,80}重构.{0,45}原图',text)
                and re.search(r'差值.{0,15}(?:趋近?于|接近)0',text)
                and re.search(r'灰度.{0,40}低像素值.{0,10}(?:黑色|深灰色)',text)):
            target=rows
        if (re.search(r'背景区域.{0,30}重构.{0,30}(?:较差|差异)',text)
                and re.search(r'差值.{0,15}(?:较大|更大)',text)
                and re.search(r'灰度.{0,30}高像素值.{0,10}(?:白色|浅灰色)',text)):
            background=rows
    if not target or not background:return []
    return list({(r.page_number,r.bbox,r.text):r for r in [*target,*background]}.values())


def paired_color_response_layout(rgb):
    import numpy as np
    import cv2
    if rgb.ndim!=3 or rgb.shape[2]!=3:return None
    height,width,_=rgb.shape
    if height<64 or width<height*3:return None
    # Subsample very large source rasters before bounded, read-only observation.
    if height>512:
        rgb=cv2.resize(rgb,(round(width*512/height),512));height,width,_=rgb.shape
    chroma=rgb.max(2).astype(float)-rgb.min(2).astype(float)
    colored=np.mean(chroma,axis=0)>3
    bounds=[0]+[i for i in range(1,width) if colored[i]!=colored[i-1]]+[width]
    runs=[(a,b,bool(colored[a])) for a,b in zip(bounds,bounds[1:]) if b-a>height*.4]
    count=len(runs)
    if count<4 or count>8 or count%2 or [r[2] for r in runs]!=[i%2==0 for i in range(count)]:return None
    if not .6<width/count/height<1.5:return None
    grid=[round(k*width/count) for k in range(count+1)]
    if any(abs(a-grid[k])>height*.12 or abs(b-grid[k+1])>height*.12 for k,(a,b,_) in enumerate(runs)):return None
    pairs=[]
    for k in range(0,count,2):
        a,b,c=grid[k:k+3];margin=max(2,round((b-a)*.12))
        source_chroma=chroma[:,a+margin:b-margin]
        response_chroma=chroma[:,b+margin:c-margin]
        if np.mean(source_chroma)<8 or np.mean(source_chroma>8)<.2 or np.mean(response_chroma)>.5:return None
        color=cv2.resize(rgb[:,a:b],(192,192));gray=cv2.resize(rgb[:,b:c],(192,192))[:,:,0]
        original=cv2.cvtColor(color,cv2.COLOR_RGB2GRAY)
        low=cv2.GaussianBlur(original.astype(float),(5,5),0)
        response=cv2.GaussianBlur(gray.astype(float),(5,5),0)
        gradient=lambda x:np.hypot(cv2.Sobel(x,cv2.CV_64F,1,0,ksize=3),cv2.Sobel(x,cv2.CV_64F,0,1,ksize=3))
        source_edges,response_edges=gradient(low),gradient(response)
        if np.std(source_edges)<1 or np.std(response_edges)<1:return None
        correlation=float(np.corrcoef(source_edges.ravel(),response_edges.ravel())[0,1])
        if not np.isfinite(correlation) or correlation<.25:return None
        design=np.column_stack([color.reshape(-1,3),np.ones(gray.size)])
        prediction=design@np.linalg.lstsq(design,gray.reshape(-1),rcond=None)[0]
        rmse=float(np.sqrt(np.mean((prediction-gray.ravel())**2)))
        low_value,high_value=[float(v) for v in np.percentile(gray,[5,95])]
        if rmse<8 or high_value-low_value<40:return None
        pairs.append(dict(source_panel=[a,0,b,height],response_panel=[b,0,c,height],
                          spatial_gradient_correlation=correlation,rgb_linear_response_rmse=rmse,
                          response_5_95_percentiles=[low_value,high_value]))
    return dict(raster_shape=list(rgb.shape),pairs=pairs,
                observation_scope='spatially paired color and nontrivial gray responses; reconstruction pixels and semantic classes are not inferred')


def _original_raster(document,area):
    import pymupdf
    import numpy as np
    roi=area['bbox'];area_size=(roi[2]-roi[0])*(roi[3]-roi[1])
    try:
        with pymupdf.open(document.path) as pdf:
            images=[]
            for item in pdf[area['page_number']-1].get_image_info(xrefs=True):
                box=item['bbox'];overlap=max(0,min(roi[2],box[2])-max(roi[0],box[0]))*max(0,min(roi[3],box[3])-max(roi[1],box[1]))
                if overlap<area_size*.8 or not item['xref']:continue
                if box[0]<roi[0]-2 or box[1]<roi[1]-2 or box[2]>roi[2]+2 or box[3]>roi[3]+2:continue
                images.append(item)
            if len(images)!=1:return None
            item=images[0];pix=pymupdf.Pixmap(pdf,item['xref'])
            if pix.n!=3 or pix.width*pix.height>16_000_000:return None
            rgb=np.frombuffer(pix.samples,dtype=np.uint8).reshape(pix.height,pix.width,3)
            observed=paired_color_response_layout(rgb)
            if observed is not None:observed.update(page_number=area['page_number'],image_bbox=list(item['bbox']))
            return observed
    except (OSError,RuntimeError,ValueError,IndexError):return None


def residual_raster_relation_proposals(context,groups,nearby):
    answer=[]
    for ordinal,areas in context['regions'].items():
        if len(areas)!=1 or not residual_response_title(areas[0]['title']):continue
        rows=_contrast_rows(_owned_passages(ordinal,groups,nearby),areas[0]['page_number'])
        if not rows:continue
        physical=_original_raster(context['_document'],areas[0])
        if physical is not None:answer.append((ordinal,'paired_reconstruction_difference_response',rows,physical))
    return answer
