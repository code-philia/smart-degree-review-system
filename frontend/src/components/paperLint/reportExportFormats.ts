import {Braces, FileDown, FileImage, FileText, FileType2} from 'lucide-react';
export const REPORT_EXPORT_FORMATS = [
  {id:'pdf', label:'PDF', icon:FileDown, color:'text-rose-600 bg-rose-50'},
  {id:'markdown', label:'Markdown', icon:FileType2, color:'text-indigo-600 bg-indigo-50'},
  {id:'text', label:'文本', icon:FileText, color:'text-amber-600 bg-amber-50'},
  {id:'docx', label:'Docx', icon:FileText, color:'text-blue-600 bg-blue-50'},
  {id:'image', label:'图片', icon:FileImage, color:'text-emerald-600 bg-emerald-50'},
  {id:'json', label:'Json', icon:Braces, color:'text-orange-600 bg-orange-50'},
] as const;
