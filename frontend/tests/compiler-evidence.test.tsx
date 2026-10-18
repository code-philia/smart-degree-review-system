import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { EvidenceLinks, CompilerDiagnostics } from '../src/components/paperLint/CompilerEvidence';
describe('compiler evidence display',()=>{
 it('shows unknown separately from violations',()=>{
  render(<CompilerDiagnostics items={[{node_id:'n1',check_id:'c1',status:'UNKNOWN',reasons:['全文尚不可达'],evidence:[]}]} />);
  expect(screen.getByText('无法判定')).toBeTruthy();expect(screen.getByText('全文尚不可达')).toBeTruthy();
 });
 it('links public HTTPS evidence and never activates unsafe URLs',()=>{
  render(<EvidenceLinks items={[{id:'a',provider:'Crossref',url:'https://api.crossref.org/works/1',quote:'A source quote'},{id:'b',url:'javascript:alert(1)',quote:'Untrusted source text'}]} />);
  expect(screen.getByRole('link').getAttribute('href')).toBe('https://api.crossref.org/works/1');
  expect(screen.getAllByRole('link')).toHaveLength(1);
 });
});
