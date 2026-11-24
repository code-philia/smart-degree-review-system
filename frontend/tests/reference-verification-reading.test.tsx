import { act, render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { afterEach, expect, it, vi } from 'vitest';
import { setLocale } from '../src/i18n/locale';
import { ReferenceVerificationDetails } from '../src/components/paperLint/ReferenceVerificationDetails';
import type { ReferenceVerificationEntry } from '../src/api/paperLint';

function sample(): ReferenceVerificationEntry {
  return { category:'incomplete', reason_code:'missing_doi',
    entry:{id:'ref-19',text:'[19]\nFAGIN R. Probabilities on finite models[J].\n1976.',title:'Probabilities on finite models',authors:['FAGIN R'],year:1976},
    matched:{title:'Probabilities on finite models',authors:['Ronald Fagin'],year:1976,doi:'10.2307/2272945'},
    comparisons:[{field:'title',cited:'Probabilities on finite models',matched:'Probabilities on finite models',status:'match'},
      {field:'doi',cited:null,matched:'10.2307/2272945',status:'missing'}],
    sources:[{provider:'openalex',url:'https://api.openalex.org/works/1',status:'success'},
      {provider:'openalex',url:'https://api.openalex.org/works?search=title',status:'success'},
      {provider:'crossref',url:'https://api.crossref.org/works?query.bibliographic=title',status:'timeout'}] };
}
afterEach(()=>act(()=>setLocale('zh')));

it.each(['zh','en'])('shows the comparison immediately and provides safe reading links (%s)',async locale=>{
  setLocale(locale);const user=userEvent.setup(),check=sample(),stored=JSON.stringify(check),selected=vi.fn();
  render(<div onClick={selected}><ReferenceVerificationDetails check={check}/></div>);
  expect(screen.getByRole('heading',{name:'[19] FAGIN R. Probabilities on finite models[J]. 1976.'})).toBeVisible();
  const table=screen.getByRole('table');expect(table).toBeVisible();
  expect(within(table).getByRole('columnheader',{name:locale==='en'?'Original citation':'原引用'})).toBeVisible();
  expect(within(table).getByRole('columnheader',{name:locale==='en'?'Database record':'数据库记录'})).toBeVisible();
  const doi=screen.getByRole('link',{name:locale==='en'?'Open DOI':'打开 DOI'});
  expect(doi).toHaveAttribute('href','https://doi.org/10.2307/2272945');
  const scholar=screen.getByRole('link',{name:'Google Scholar'}),baidu=screen.getByRole('link',{name:locale==='en'?'Baidu Scholar':'百度学术'});
  expect(new URL(scholar.getAttribute('href')!).searchParams.get('q')).toBe(check.entry.title);
  expect(new URL(baidu.getAttribute('href')!).searchParams.get('wd')).toBe(check.entry.title);
  for(const link of [doi,scholar,baidu]){expect(link).toHaveAttribute('target','_blank');expect(link).toHaveAttribute('rel','noopener noreferrer');}
  expect(screen.queryByText(locale==='en'?'Verification sources':'核验来源',{exact:true})).not.toBeInTheDocument();
  expect(screen.queryByRole('link',{name:'OpenAlex'})).not.toBeInTheDocument();
  // Link actions must not trigger the surrounding PDF-selection card.
  selected.mockClear();await user.click(scholar);expect(selected).not.toHaveBeenCalled();
  expect(JSON.stringify(check)).toBe(stored);
});

it('keeps unresolved references readable and searchable without inventing a DOI',()=>{
  const check=sample();check.category='unverified';check.reason_code='provider_unavailable';check.matched=null;check.comparisons=[];
  render(<ReferenceVerificationDetails check={check}/>);
  expect(screen.queryByRole('table')).not.toBeInTheDocument();expect(screen.queryByRole('link',{name:'打开 DOI'})).not.toBeInTheDocument();
  expect(screen.getByRole('link',{name:'Google Scholar'})).toBeVisible();
  expect(screen.getByText(/未核验不表示引用存在问题/)).toBeVisible();
});

it('uses an encoded, fixed-host DOI URL and never makes an arbitrary identifier clickable',()=>{
  const check=sample();check.entry.doi='10.1002/35:3<222::aid-jgt7>3.0.co;2-#';
  const {rerender}=render(<ReferenceVerificationDetails check={check}/>);
  const url=new URL(screen.getByRole('link',{name:'打开 DOI'}).getAttribute('href')!);
  expect(url.hostname).toBe('doi.org');expect(url.hash).toBe('');expect(url.search).toBe('');expect(url.pathname).toContain('%3C');
  check.entry.doi='javascript:alert(1)';check.matched!.doi='https://evil.example/private';
  rerender(<ReferenceVerificationDetails check={check}/>);expect(screen.queryByRole('link',{name:'打开 DOI'})).not.toBeInTheDocument();
});

it('builds search links from escaped citation text when a parsed title is unavailable',()=>{
  const check=sample();check.entry.title='';check.entry.text='[19]\nA title & method "example"? <script> 2024.';check.matched=null;
  render(<ReferenceVerificationDetails check={check}/>);
  const url=new URL(screen.getByRole('link',{name:'Google Scholar'}).getAttribute('href')!);
  expect(url.hostname).toBe('scholar.google.com');expect(url.searchParams.get('q')).toContain('A title & method');
  expect(document.querySelector('script')).toBeNull();
});

it.each(['zh','en'])('keeps related-version and unresolved field interpretations visible without hover (%s)',locale=>{
  setLocale(locale);const check=sample();check.comparisons=[
    {field:'year',cited:2023,matched:2024,status:'equivalent'},
    {field:'authors',cited:['A'],matched:['B'],status:'unknown'},
    {field:'doi',cited:null,matched:'10.2307/2272945',status:'missing'}];
  render(<ReferenceVerificationDetails check={check}/>);const table=screen.getByRole('table');
  for(const label of locale==='en'?['Related version','Needs review','Missing']:['相关版本','待核查','缺失']){
    expect(within(table).getByText(label,{exact:true})).toBeVisible();
  }
});
