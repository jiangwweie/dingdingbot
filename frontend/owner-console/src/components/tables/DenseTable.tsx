import {
  tableFeatures,
  useTable,
  type ColumnDef,
  type RowData,
} from "@tanstack/react-table";
import { Fragment, type ReactNode } from "react";

const denseTableFeatures = tableFeatures({});

export type DenseTableColumnDef<TData extends RowData> = ColumnDef<
  typeof denseTableFeatures,
  TData,
  unknown
>;

interface DenseTableProps<TData extends RowData> {
  ariaLabel: string;
  columnWidths?: readonly string[];
  columns: DenseTableColumnDef<TData>[];
  data: TData[];
  expandedRowId?: string | null;
  getRowId: (row: TData) => string;
  renderExpandedRow?: (row: TData, columnCount: number) => ReactNode;
}

export function DenseTable<TData extends RowData>({
  ariaLabel,
  columnWidths,
  columns,
  data,
  expandedRowId = null,
  getRowId,
  renderExpandedRow,
}: DenseTableProps<TData>) {
  const table = useTable({
    columns,
    data,
    features: denseTableFeatures,
    getRowId,
  });

  return (
    <div className="w-full overflow-x-auto rounded-[var(--radius-panel)] border border-[var(--color-divider)] bg-[var(--color-surface)] shadow-[var(--shadow-decorative)]">
      <table className="w-full min-w-[960px] table-fixed border-collapse text-left" aria-label={ariaLabel}>
        {columnWidths ? (
          <colgroup>
            {columnWidths.map((width, index) => <col key={`${index}:${width}`} style={{ width }} />)}
          </colgroup>
        ) : null}
        <thead className="h-[32px] border-b border-[var(--color-divider)] bg-[var(--color-surface-secondary)] text-[11px] font-semibold uppercase tracking-wider text-[var(--color-text-secondary)]">
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th className="px-3 align-middle font-semibold" key={header.id} scope="col">
                  {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody className="divide-y divide-[var(--color-divider)]">
          {table.getRowModel().rows.map((row) => (
            <Fragment key={row.id}>
              <tr
                className="h-[38px] text-[12px] transition-colors duration-150 hover:bg-[#20252e]"
                key={row.id}
              >
                {row.getAllCells().map((cell) => (
                  <td className="px-3 align-middle text-[var(--color-text-primary)]" key={cell.id}>
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
              {expandedRowId === row.id && renderExpandedRow
                ? renderExpandedRow(row.original, row.getAllCells().length)
                : null}
            </Fragment>
          ))}
        </tbody>
      </table>
    </div>
  );
}
