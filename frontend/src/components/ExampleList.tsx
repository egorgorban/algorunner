/**
 * Dynamic example list component with add/remove rows (UI-01, D-08).
 * Each row has input, output, and optional explanation fields.
 */

import * as React from "react";

interface ExampleRow {
  input: string;
  output: string;
  explanation: string;
}

interface ExampleListProps {
  rows: ExampleRow[];
  maxRows: number;
  rowErrors: Record<number, string>;
  onChange(rows: ExampleRow[]): void;
}

export function ExampleList({
  rows,
  maxRows,
  rowErrors,
  onChange,
}: ExampleListProps): React.ReactElement {
  const handleRowChange = (index: number, field: keyof ExampleRow, value: string): void => {
    const newRows = [...rows];
    const row = newRows[index];
    if (row) {
      newRows[index] = { ...row, [field]: value };
      onChange(newRows);
    }
  };

  const handleAddRow = (): void => {
    if (rows.length < maxRows) {
      onChange([...rows, { input: "", output: "", explanation: "" }]);
    }
  };

  const handleDeleteRow = (index: number): void => {
    onChange(rows.filter((_, i) => i !== index));
  };

  return (
    <div className="space-y-4">
      <h3 className="text-sm font-semibold text-gray-700">Примеры</h3>

      {rows.map((row, index) => (
        <div key={index} className="border border-gray-300 rounded-md p-4 space-y-3">
          <div>
            <label htmlFor={`input-${index}`} className="block text-xs font-medium text-gray-700 mb-1">
              Вход
            </label>
            <textarea
              id={`input-${index}`}
              value={row.input}
              onChange={(e) => handleRowChange(index, "input", e.target.value)}
              placeholder="Введите входные данные..."
              className="w-full h-20 px-3 py-2 border border-gray-300 rounded-md font-mono text-sm"
            />
          </div>

          <div>
            <label htmlFor={`output-${index}`} className="block text-xs font-medium text-gray-700 mb-1">
              Выход
            </label>
            <textarea
              id={`output-${index}`}
              value={row.output}
              onChange={(e) => handleRowChange(index, "output", e.target.value)}
              placeholder="Введите ожидаемый результат..."
              className="w-full h-20 px-3 py-2 border border-gray-300 rounded-md font-mono text-sm"
            />
          </div>

          <div>
            <label htmlFor={`explanation-${index}`} className="block text-xs font-medium text-gray-700 mb-1">
              Пояснение (опционально)
            </label>
            <input
              id={`explanation-${index}`}
              type="text"
              value={row.explanation}
              onChange={(e) => handleRowChange(index, "explanation", e.target.value)}
              placeholder="Объяснение примера..."
              className="w-full px-3 py-2 border border-gray-300 rounded-md text-sm"
            />
          </div>

          {rowErrors[index] && (
            <div className="text-sm text-red-600 font-medium">{rowErrors[index]}</div>
          )}

          <button
            type="button"
            onClick={() => handleDeleteRow(index)}
            className="text-sm text-red-600 hover:text-red-800 font-medium"
          >
            Удалить
          </button>
        </div>
      ))}

      <button
        type="button"
        onClick={handleAddRow}
        disabled={rows.length >= maxRows}
        className={`text-sm font-medium py-2 px-4 rounded-md ${
          rows.length >= maxRows
            ? "bg-gray-100 text-gray-400 cursor-not-allowed"
            : "bg-blue-100 text-blue-700 hover:bg-blue-200"
        }`}
      >
        Добавить пример
      </button>
    </div>
  );
}
