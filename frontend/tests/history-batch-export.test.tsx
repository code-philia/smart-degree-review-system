import {act,fireEvent,render,screen,waitFor,within} from '@testing-library/react';
import {useState} from 'react';
import {MemoryRouter} from 'react-router-dom';
import {beforeEach,expect,it,vi} from 'vitest';
import {ReportHistoryTable} from '../src/components/paperLint/ReportHistoryTable';
import {setLocale} from '../src/i18n/locale';
import {createBatchReportFile} from '../src/utils/reportExport/batch';
import {downloadReportFile} from '../src/utils/reportExport/formats';
vi.mock('../src/utils/reportExport/batch',()=>({createBatchReportFile:vi.fn()}));
vi.mock('../src/utils/reportExport/formats',()=>({downloadReportFile:vi.fn()}));
const rows=Array.from({length:8},(_,i)=>({id:String(i),source_filename:`${i%2?'乙':'甲'}论文${i}.pdf`,created_at:'2026-11-19T00:00:00Z',summary:{finding_count:0,error_rule_count:0,unsupported_rule_count:0}})) as any;
function History(){const [selected,setSelected]=useState<string[]>([]);return <MemoryRouter><ReportHistoryTable reports={rows} historyPath="/reports" selectedReportIds={selected} onSelectionChange={setSelected} deleting={false} onDelete={()=>{}}/></MemoryRouter>;}
beforeEach(()=>{setLocale('zh');vi.clearAllMocks();vi.mocked(createBatchReportFile).mockResolvedValue({filename:'reports.zip',blob:new Blob(['zip'])});});
function show(){render(<History/>);fireEvent.click(screen.getByRole('button',{name:'批量管理',exact:true}));}
it('distinguishes page selection from all-report selection and keeps the latter across pages',()=>{
  show();fireEvent.click(screen.getByRole('button',{name:'全选本页',exact:true}));
  expect(screen.getByRole('button',{name:'导出选中（5）'})).toBeEnabled();
  fireEvent.click(screen.getByRole('button',{name:'全选全部报告',exact:true}));
  expect(screen.getByRole('button',{name:'导出选中（8）'})).toBeEnabled();
  fireEvent.click(screen.getByRole('button',{name:'下一页'}));
  for(const checkbox of screen.getAllByRole('checkbox'))expect(checkbox).toBeChecked();
  fireEvent.click(screen.getByRole('button',{name:'清空选择',exact:true}));
  expect(screen.getByRole('button',{name:'导出选中（0）'})).toBeDisabled();
});
it('selects only search matches and exports all selected reports through the real dialog',async()=>{
  show();fireEvent.change(screen.getByRole('searchbox'),{target:{value:'甲'}});
  fireEvent.click(screen.getByRole('button',{name:'全选搜索结果',exact:true}));
  fireEvent.click(screen.getByRole('button',{name:'导出选中（4）'}));
  const dialog=screen.getByRole('dialog',{name:'批量导出报告'});
  fireEvent.click(within(dialog).getByRole('button',{name:'导出 文本'}));
  await waitFor(()=>expect(downloadReportFile).toHaveBeenCalledTimes(1));
  expect(createBatchReportFile).toHaveBeenCalledWith(['0','2','4','6'],'text',expect.objectContaining({locale:'zh'}));
  expect(within(dialog).getByRole('status')).toHaveTextContent('4');
});
it('cancels without downloading and keeps the chosen export language after switching UI language',async()=>{
  show();fireEvent.click(screen.getByRole('button',{name:'全选全部报告',exact:true}));
  fireEvent.click(screen.getByRole('button',{name:'导出选中（8）'}));
  let resolve!:(value:any)=>void;vi.mocked(createBatchReportFile).mockReturnValue(new Promise(r=>{resolve=r;}));
  fireEvent.click(within(screen.getByRole('dialog')).getByRole('button',{name:'导出 PDF'}));
  act(()=>setLocale('en'));
  expect(within(screen.getByRole('dialog')).getByRole('status')).toHaveTextContent('Packaging reports: 0 / 8');
  const options=vi.mocked(createBatchReportFile).mock.calls[0][2];expect(options?.locale).toBe('zh');
  fireEvent.click(screen.getByRole('button',{name:'Cancel export'}));
  expect(options?.signal?.aborted).toBe(true);
  await act(async()=>resolve({filename:'cancelled.zip',blob:new Blob()}));
  expect(downloadReportFile).not.toHaveBeenCalled();
});
it('localizes the complete English selection and export flow while preserving thesis filenames',()=>{
  setLocale('en');render(<History/>);
  fireEvent.click(screen.getByRole('button',{name:'Manage records',exact:true}));
  fireEvent.click(screen.getByRole('button',{name:'Select all reports',exact:true}));
  fireEvent.click(screen.getByRole('button',{name:'Export selected (8)',exact:true}));
  const dialog=screen.getByRole('dialog',{name:'Export selected reports'});
  expect(within(dialog).getByText('8 reports selected')).toBeVisible();
  expect(within(dialog).getByRole('button',{name:'Export Text'})).toBeEnabled();
});
