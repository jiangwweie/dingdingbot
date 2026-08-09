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
  columns: DenseTableColumnDef<TData>[];
  data: TData[];
  expandedRowId?: string | null;
  getRowId: (row: TData) => string;
  renderExpandedRow?: (row: TData, columnCount: number) => ReactNode;
}

export function DenseTable<TData extends RowData>({
  ariaLabel,
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
    <div className="w-full overflow-x-auto border border-[var(--color-divider)] bg-[var(--color-surface)]">
      <table className="w-full min-w-[960px] table-fixed border-collapse text-left" aria-label={ariaLabel}>
        <thead className="h-[30px] border-b border-[var(--color-divider)] bg-[var(--color-surface-secondary)] text-[11px] font-medium text-[var(--color-text-secondary)]">
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id}>
              {headerGroup.headers.map((header) => (
                <th className="px-2 align-middle font-medium" key={header.id} scope="col">
                  {header.isPlaceholder ? null : <table.FlexRender header={header} />}
                </th>
              ))}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <Fragment key={row.id}>
              <tr
                className="h-[38px] border-b border-[var(--color-divider)] text-[12px] last:border-b-0 hover:bg-[var(--color-surface-secondary)]"
                key={row.id}
              >
                {row.getAllCells().map((cell) => (
                  <td className="px-2 align-middle" key={cell.id}>
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
