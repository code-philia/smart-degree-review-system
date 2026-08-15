import type { HTMLAttributes, ReactNode, TableHTMLAttributes, TdHTMLAttributes, ThHTMLAttributes } from 'react';

type DataTableProps = HTMLAttributes<HTMLElement> & {
  children: ReactNode;
  tableClassName?: string;
  tableProps?: TableHTMLAttributes<HTMLTableElement>;
};

/**
 * Shared visual foundation for operational lists.
 *
 * Report-detail tables intentionally do not use this component: they retain
 * their document-like layout. Use DataTable for records, queues and ledgers.
 */
function DataTable({ children, className = '', tableClassName = '', tableProps, ...rest }: DataTableProps) {
  return (
    <section className={`overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm ${className}`} {...rest}>
      <div className="w-full overflow-x-auto">
        <table className={`w-full border-collapse text-sm text-slate-700 ${tableClassName}`} {...tableProps}>
          {children}
        </table>
      </div>
    </section>
  );
}

function DataTableHead({ children, className = '', ...rest }: ThHTMLAttributes<HTMLTableCellElement>) {
  return (
    <th
      scope="col"
      className={`h-11 bg-slate-50 px-4 py-3 text-left text-xs font-bold tracking-wide text-slate-600 ${className}`}
      {...rest}
    >
      {children}
    </th>
  );
}

function DataTableRow({ className = '', ...rest }: HTMLAttributes<HTMLTableRowElement>) {
  return (
    <tr
      className={`border-b border-slate-100 transition-colors last:border-b-0 hover:bg-brand-50/60 ${className}`}
      {...rest}
    />
  );
}

function DataTableCell({ children, className = '', ...rest }: TdHTMLAttributes<HTMLTableCellElement>) {
  return (
    <td className={`px-4 py-3 align-middle leading-5 ${className}`} {...rest}>
      {children}
    </td>
  );
}

export { DataTable, DataTableCell, DataTableHead, DataTableRow };
