import type { ListingsQuery } from "@/lib/api";

interface FilterBarProps {
  current: ListingsQuery;
}

export function FilterBar({ current }: FilterBarProps) {
  return (
    <form
      method="GET"
      className="panel p-4 grid grid-cols-2 md:grid-cols-6 gap-3"
    >
      <TextInput
        name="q"
        label="Search"
        defaultValue={current.q}
        placeholder="2018 f-150, diesel, low miles…"
        span={2}
      />
      <TextInput name="make" label="Make" defaultValue={current.make} placeholder="Ford" />
      <TextInput name="model" label="Model" defaultValue={current.model} placeholder="F-150" />
      <TextInput
        name="year_min"
        label="Year ≥"
        type="number"
        defaultValue={current.year_min?.toString()}
      />
      <TextInput
        name="price_max"
        label="Price ≤"
        type="number"
        defaultValue={current.price_max?.toString()}
      />
      <TextInput name="zip" label="ZIP" defaultValue={current.zip} placeholder="33607" />
      <TextInput
        name="near_zip"
        label="Near ZIP"
        defaultValue={current.near_zip}
        placeholder="33607"
      />
      <TextInput
        name="radius_miles"
        label="Radius mi"
        type="number"
        defaultValue={current.radius_miles?.toString()}
        placeholder="100"
      />
      <Select
        name="classification"
        label="Class"
        defaultValue={current.classification ?? "private_seller"}
        options={[
          { value: "private_seller", label: "Private sellers" },
          { value: "", label: "All" },
          { value: "dealer", label: "Dealers" },
          { value: "scam", label: "Scams" },
          { value: "uncertain", label: "Uncertain" },
        ]}
      />
      <TextInput
        name="mileage_max"
        label="Mileage ≤"
        type="number"
        defaultValue={current.mileage_max?.toString()}
      />
      <TextInput
        name="min_score"
        label="Score ≥"
        type="number"
        defaultValue={current.min_score?.toString()}
        placeholder="60"
      />
      <Select
        name="sort"
        label="Sort"
        defaultValue={current.sort ?? "posted_at"}
        options={[
          { value: "posted_at", label: "Newest first" },
          { value: "score", label: "Highest score" },
          { value: "price", label: "Lowest price" },
        ]}
      />
      <div className="col-span-2 md:col-span-6 flex items-center justify-between border-t border-ink-200 pt-3">
        <p className="text-xs text-ink-500">
          Filters apply server-side. Use search for full-text across title + description.
        </p>
        <button type="submit" className="btn-primary">
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
  span = 1,
}: {
  name: string;
  label: string;
  defaultValue?: string;
  placeholder?: string;
  type?: string;
  span?: 1 | 2;
}) {
  return (
    <label className={`flex flex-col gap-1 ${span === 2 ? "col-span-2" : ""}`}>
      <span className="label">{label}</span>
      <input
        name={name}
        type={type}
        defaultValue={defaultValue ?? ""}
        placeholder={placeholder}
        className="input"
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
    <label className="flex flex-col gap-1">
      <span className="label">{label}</span>
      <select name={name} defaultValue={defaultValue} className="input">
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
