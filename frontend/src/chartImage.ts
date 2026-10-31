/** Turns a chart on the page into a PNG file: its SVG drawn on a canvas, with the title and legend added, since those
 * are HTML around the SVG. */

const SCALE = 2
const TITLE_HEIGHT = 32
const LEGEND_HEIGHT = 62
const FONT = 'system-ui, sans-serif'

/** A saved SVG has no page around it, so each CSS variable must become its value. */
export function resolveVariables(markup: string, valueOf: (name: string) => string): string {
  return markup.replace(/var\((--[\w-]+)\)/g, (_, name: string) => valueOf(name).trim())
}

/** The file name of a chart: its title's first words, in lower case. */
export function pngName(title: string): string {
  return `${title.split('(')[0].trim().toLowerCase().replaceAll(' ', '-')}.png`
}

function loadImage(url: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    image.onload = () => resolve(image)
    image.onerror = () => reject(new Error('The chart could not be drawn as an image'))
    image.src = url
  })
}

function drawLegend(context: CanvasRenderingContext2D, color: (name: string) => string, y: number) {
  context.font = `12px ${FONT}`
  context.fillStyle = color('--color-stack-a')
  context.fillText('Stack A (filled)', 16, y)
  context.fillStyle = color('--color-stack-b')
  context.fillText('Stack B (hollow)', 130, y)
  context.fillStyle = color('--color-muted')
  context.fillText('Bars: 95% interval.', 16, y + 18)
  context.fillText('+ or -: real change from the step before.', 16, y + 34)
}

/** Save the chart inside `figure` as a PNG, with the page's current colours. Its legend icons are small SVGs of the same
 * class, and they come first. */
export async function downloadChart(figure: HTMLElement, title: string) {
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
  canvas.width = width * SCALE
  canvas.height = (height + TITLE_HEIGHT + LEGEND_HEIGHT) * SCALE
  const context = canvas.getContext('2d')!
  context.scale(SCALE, SCALE)
  context.fillStyle = color('--color-panel')
  context.fillRect(0, 0, width, height + TITLE_HEIGHT + LEGEND_HEIGHT)
  context.fillStyle = color('--color-ink')
  context.font = `600 14px ${FONT}`
  context.fillText(title, 16, 22)
  context.drawImage(image, 0, TITLE_HEIGHT, width, height)
  drawLegend(context, color, height + TITLE_HEIGHT + 18)
  const link = document.createElement('a')
  link.href = canvas.toDataURL('image/png')
  link.download = pngName(title)
  link.click()
}
