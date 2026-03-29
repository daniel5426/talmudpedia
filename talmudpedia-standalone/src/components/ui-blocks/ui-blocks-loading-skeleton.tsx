export function UIBlocksLoadingSkeleton() {
  return (
    <div className="space-y-4">
      <div className="space-y-2">
        <div className="h-3 w-40 bg-slate-900/10" />
        <div className="h-3 w-56 bg-slate-900/5" />
      </div>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-12">
        {Array.from({ length: 4 }).map((_, index) => (
          <div
            key={`kpi-${index}`}
            className="col-span-1 border-b border-slate-200 bg-transparent p-4 md:col-span-3"
          >
            <div className="h-3 w-20 bg-slate-900/5" />
            <div className="mt-4 h-8 w-16 bg-slate-900/10" />
          </div>
        ))}
      </div>
    </div>
  );
}
