/** A page's name and, under it, what the page is for in one line. */
export default function PageTitle({ title, about }: { title: string; about: string }) {
  return (
    <div>
      <h1 className="text-2xl font-bold tracking-tight">{title}</h1>
      <p className="text-muted">{about}</p>
    </div>
  )
}
