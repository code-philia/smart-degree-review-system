"""Display locations preserve the distinction between source and synthetic text."""
import copy

def present(ir,report):
    output=copy.deepcopy(report);nodes={n['id']:n for n in ir['nodes']};pages={p['page_index']:p for p in ir['layout']['pages']}
    evidence={e['id']:e for e in report.get('evidence',[])}
    def sources(items):
        found=[]
        for item in items:
            if item.get('kind')=='synthetic':return None
            if item.get('bbox') is not None and item.get('page_index') in pages:found.append(item)
            nested=sources(item.get('ancestor_provenance',[]))
            if nested is None:return None
            found.extend(nested)
        return found
    for rule in output['rules']:
        for row in rule['results']:
            node=nodes.get(row.get('node_id'),{});spans=sources(row.get('provenance',[]));rects=[]
            row['location_mode']='synthetic' if spans is None else 'source' if spans else 'unlocated'
            for span in spans or []:
                page=pages[span['page_index']];w,h=page['width'],page['height'];rotation=page.get('rotation',0)
                x1,y1,x2,y2=span['bbox'];points=[(x,y) for x in [x1,x2] for y in [y1,y2]]
                points=[(h-y,x) if rotation==90 else (w-x,h-y) if rotation==180 else (y,w-x) if rotation==270 else (x,y) for x,y in points]
                rects.append({'x1':min(x for x,y in points),'y1':min(y for x,y in points),'x2':max(x for x,y in points),'y2':max(y for x,y in points),
                    'width':h if rotation in [90,270] else w,'height':w if rotation in [90,270] else h,'page_number':span['page_index']+1})
            row['location']={'type':'pdf_bbox','page_number':rects[0]['page_number'],'bounding_rect':rects[0],'rects':rects,'text_excerpt':str(node.get('text') or '')[:1000]} if rects else None
            display=[]
            for eid in row.get('evidence_ids',[]):
                item=evidence.get(eid,{})
                display.append({'id':eid,'kind':item.get('kind','source_node'),'provider':item.get('provider'),
                    'url':item.get('query_url') or item.get('source_url') or item.get('url'),
                    'quote':str(item.get('quote') or item.get('text') or nodes.get(eid,{}).get('text') or '')[:1000]})
            row['display_evidence']=display
    # Full evidence remains in the saved check artifact; the UI protocol carries selected excerpts.
    output.pop('evidence',None);output.pop('bindings',None)
    return output
