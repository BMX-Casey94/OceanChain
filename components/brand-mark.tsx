import Link from "next/link"

type BrandMarkProps = {
  href?: string
  subtitle?: string
  compact?: boolean
}

export function BrandMark({
  href = "/",
  subtitle = "Maritime intelligence on Bitcoin",
  compact = false,
}: BrandMarkProps) {
  const inner = (
    <>
      <div className="flex items-baseline">
        <span className="font-heading text-2xl tracking-[0.12em] text-teal-300">OCE</span>
        <span className="font-heading text-2xl tracking-[0.12em] text-white">CHAIN</span>
      </div>
      {!compact && (
        <span className="block text-[11px] text-muted-foreground font-sans -mt-0.5 tracking-wide">
          {subtitle}
        </span>
      )}
    </>
  )

  if (href) {
    return (
      <Link href={href} className="group inline-flex flex-col" aria-label="Ocechain home">
        {inner}
      </Link>
    )
  }
  return <div className="inline-flex flex-col">{inner}</div>
}
