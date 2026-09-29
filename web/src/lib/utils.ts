import { clsx, type ClassValue } from 'clsx'
import { twMerge } from 'tailwind-merge'

export const cn = (...inputs: ClassValue[]) => twMerge(clsx(inputs))

/** Valid date for a lead, from an ISO init time. */
export function validDate(init: string, lead: number) {
  const d = new Date(init)
  d.setUTCDate(d.getUTCDate() + lead)
  return d.toISOString().slice(0, 10)
}
