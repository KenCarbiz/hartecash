import type { ListingsQuery } from "@/lib/api";

interface FilterBarProps {
  current: ListingsQuery;
}

export function FilterBar({ current }: FilterBarProps) {
  return (
    <form
      method="GET"
      className="rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-4 grid grid-cols-2 md:grid-cols-6 gap-3"
    >
      <TextInput name="make" label="Make" defaultValue={current.make} placeholder="Ford" />
      <TextInput name="model" label="Model" defaultValue={current.model} placeholder="F-150" />
      <TextInput
        name="year_min"
        label="Year min"
        type="number"
        defaultValue={current.year_min?.toString()}
      />
      <TextInput
        name="price_max"
        label="Price max"
        type="number"
        defaultValue={current.price_max?.toString()}
      />
      <TextInput name="zip" label="ZIP" defaultValue={current.zip} placeholder="33607" />
      <Select
        name="classification"
        label="Classification"
        defaultValue={current.classification ?? "private_seller"}
        options={[
          { value: "private_seller", label: "Private sellers" },
          { value: "", label: "All" },
          { value: "dealer", label: "Dealers" },
          { value: "scam", label: "Scams" },
          { value: "uncertain", label: "Uncertain" },
        ]}
      />
      <div className="col-span-2 md:col-span-6 flex justify-end">
        <button
          type="submit"
          className="rounded-md bg-brand-600 px-4 py-2 text-sm font-medium text-white hover:bg-brand-700"
        >
          Apply filters
        </button>
      </div>
    </form>
  );
}

function TextInput({
  name,
  label,
  defaultValue,
  placeholder,
  type = "text",
}: {
  name: string;
  label: string;
  defaultValue?: string;
  placeholder?: string;
  type?: string;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-500">
      {label}
      <input
        name={name}
        type={type}
        defaultValue={defaultValue ?? ""}
        placeholder={placeholder}
        className="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-2 py-1.5 text-sm text-slate-900 dark:text-slate-100"
      />
    </label>
  );
}

function Select({
  name,
  label,
  defaultValue,
  options,
}: {
  name: string;
  label: string;
  defaultValue?: string;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex flex-col gap-1 text-xs text-slate-500">
      {label}
      <select
        name={name}
        defaultValue={defaultValue}
        className="rounded-md border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-950 px-2 py-1.5 text-sm text-slate-900 dark:text-slate-100"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
