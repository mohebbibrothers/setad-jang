/**
 * EmptyState — used by every paginated section when the backend
 * returns zero items. Renders a quiet, dignified placeholder with a
 * brand-tinted icon disc and a one-line description.
 *
 * The wrapper takes full row width (`w-full` + `basis-full`) so when it
 * lives inside a flex/grid parent it always centres on its own line
 * instead of clinging to the RTL-right edge.
 */
export function EmptyState({
  title,
  description,
  iconPath,
}: {
  title: string;
  description?: string;
  /** Single SVG path 'd' attribute. Keeps the component dep-free.
   *  Use ' M …' multi-subpath strings when you need multiple strokes. */
  iconPath: string;
}) {
  return (
    <div
      className="w-full basis-full flex flex-col items-center text-center
                 py-12 md:py-16 px-4"
    >
      <div
        className="mb-5 w-16 h-16 rounded-2xl
                   bg-gradient-to-br from-brand-50 to-brand-100
                   text-brand-600 flex items-center justify-center
                   shadow-[inset_0_0_0_1px_rgba(13,128,116,.08)]"
        aria-hidden="true"
      >
        <svg
          width="28" height="28" viewBox="0 0 24 24" fill="none"
          stroke="currentColor" strokeWidth={1.8}
          strokeLinecap="round" strokeLinejoin="round"
        >
          <path d={iconPath} />
        </svg>
      </div>
      <h3 className="text-[15px] md:text-[16px] font-extrabold text-ink-900 max-w-md">
        {title}
      </h3>
      {description && (
        <p className="mt-2 text-[12.5px] md:text-[13px] text-ink-500 font-medium leading-7 max-w-md">
          {description}
        </p>
      )}
    </div>
  );
}
