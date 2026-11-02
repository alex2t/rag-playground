/** Turns a chart on the page into a PNG file: its SVG drawn on a canvas, with the title and legend added, since those
 * are HTML around the SVG. */

const SCALE = 2
const TITLE_HEIGHT = 32
const LINE_HEIGHT = 16
const MARGIN = 16
const SWATCH = 10
const FONT = 'system-ui, sans-serif'

/** One line under the chart; a swatch names the CSS colour of the marks it describes. */
export type LegendLine = { text: string; swatch?: string }

/** A saved SVG has no page around it, so each CSS variable must become its value. */
export function resolveVariables(markup: string, valueOf: (name: string) => string): string {
  return markup.replace(/var\((--[\w-]+)\)/g, (_, name: string) => valueOf(name).trim())
}

/** The file name of a chart: its title's first words, in lower case. */
export function pngName(title: string): string {
  return `${title.split('(')[0].trim().toLowerCase().replaceAll(' ', '-')}.png`
}

/** Text broken at spaces into rows that fit. A single word too long for a row keeps a row of its own. */
export function wrapText(text: string, fits: (row: string) => boolean): string[] {
  const rows: string[] = []
  let row = ''
  for (const word of text.split(' ')) {
    const longer = row ? `${row} ${word}` : word
    if (row && !fits(longer)) {
      rows.push(row)
      row = word
    } else {
      row = longer
    }
  }
  return [...rows, row]
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('The chart could not be drawn as an image'))
    image.src = url
  })
}

type Row = { text: string; swatch?: string }

function legendRows(context: CanvasRenderingContext2D, legend: LegendLine[], width: number): Row[] {
  context.font = `12px ${FONT}`
  return legend.flatMap(({ text, swatch }) => {
    const room = width - 2 * MARGIN - (swatch ? SWATCH + 6 : 0)
    return wrapText(text, (row) => context.measureText(row).width <= room)
      .map((row, index) => ({ text: row, swatch: index === 0 ? swatch : undefined, indent: swatch ? SWATCH + 6 : 0 }))
  })
}

function drawLegend(context: CanvasRenderingContext2D, rows: (Row & { indent?: number })[], color: (name: string) => string, top: number) {
  context.font = `12px ${FONT}`
  rows.forEach(({ text, swatch, indent = 0 }, index) => {
    const y = top + index * LINE_HEIGHT
    if (swatch) {
      context.fillStyle = color(swatch)
      context.fillRect(MARGIN, y - SWATCH, SWATCH, SWATCH)
    }
    context.fillStyle = color('--color-muted')
    context.fillText(text, MARGIN + indent, y)
  })
}

/** Save the chart inside `figure` as a PNG, with the page's current colours. Its legend icons are small SVGs of the same
 * class, and they come first. */
export async function downloadChart(figure: HTMLElement, title: string, legend: LegendLine[]) {
  const svg = [...figure.querySelectorAll<SVGSVGElement>('svg.recharts-surface')]
    .find((candidate) => !candidate.closest('.recharts-legend-wrapper'))
  if (!svg) throw new Error('The chart is not drawn yet')
  const styles = getComputedStyle(document.documentElement)
  const color = (name: string) => styles.getPropertyValue(name).trim()
  const { width, height } = svg.getBoundingClientRect()
  const clone = svg.cloneNode(true) as SVGSVGElement
  clone.setAttribute('xmlns', 'http://www.w3.org/2000/svg')
  clone.setAttribute('width', String(width))
  clone.setAttribute('height', String(height))
  clone.style.fontFamily = FONT
  const markup = resolveVariables(new XMLSerializer().serializeToString(clone), color)
  const image = await loadImage(`data:image/svg+xml;charset=utf-8,${encodeURIComponent(markup)}`)
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d')!
  const rows = legendRows(context, legend, width)
  const total = height + TITLE_HEIGHT + LINE_HEIGHT * rows.length + LINE_HEIGHT
  canvas.width = width * SCALE
  canvas.height = total * SCALE
  context.scale(SCALE, SCALE)
  context.fillStyle = color('--color-panel')
  context.fillRect(0, 0, width, total)
  context.fillStyle = color('--color-ink')
  context.font = `600 14px ${FONT}`
  context.fillText(title, MARGIN, 22)
  context.drawImage(image, 0, TITLE_HEIGHT, width, height)
  drawLegend(context, rows, color, height + TITLE_HEIGHT + LINE_HEIGHT + 2)
  const link = document.createElement('a')
  link.href = canvas.toDataURL('image/png')
  link.download = pngName(title)
  link.click()
}
