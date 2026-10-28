/** Column names of a price CSV, mirroring the server's rule: a first column
 *  that is not a number is a date column and is skipped. */
export function priceColumns(csv: string): string[] {
  const rows = csv.split(/\r?\n/).filter((r) => r.trim() !== '')
  if (rows.length < 2) return []
  const header = rows[0].split(',').map((c) => c.trim())
  const first = rows[1].split(',')[0].replace(/[,$]/g, '').trim()
  const hasDates = first === '' || Number.isNaN(Number(first))
  return (hasDates ? header.slice(1) : header).filter(Boolean)
}
