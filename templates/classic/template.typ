// Floresu "Classic" resume template.
//
// Original work authored for Floresu. It follows the widely used single-page,
// single-column technical-resume layout (a bold centered name, a contact line,
// ruled uppercase section headings, and tight bullet lists in a standard serif
// font). That structure keeps the output ATS-safe by construction: real
// selectable text, a logical top-to-bottom reading order, standard embedded
// fonts, and plain-text headings and list items. Colors, fonts, and layout are
// fixed here and are not caller-overridable.
//
// The resume data arrives as a decoded dictionary (see main.typ), never as Typst
// source, so arbitrary user text is content and can never inject markup.

#let _body-font = "New Computer Modern"

// The centered header: the name, then the present contact lines and links joined
// by a thin separator. The input mapper drops absent fields, so nothing here
// renders a placeholder for a missing value.
#let header(full-name, contact, links) = {
  if full-name != "" {
    align(center, text(size: 19pt, weight: "bold", full-name))
  }
  let parts = contact + links.map(item => link(item.url, item.label))
  if parts.len() > 0 {
    v(3pt)
    align(center, text(size: 9.5pt, parts.join("  |  ")))
  }
}

// A section heading: an uppercase, letter-spaced title above a full-width rule.
#let section-heading(title) = {
  v(9pt)
  text(size: 10.5pt, weight: "bold", tracking: 0.6pt, upper(title))
  v(2pt)
  line(length: 100%, stroke: 0.5pt + black)
  v(3pt)
}

// A tight bullet list of plain-text lines (hanging indent for wrapped lines).
#let bullet-list(items) = list(
  marker: [•],
  indent: 0pt,
  body-indent: 6pt,
  spacing: 4pt,
  ..items,
)

// The summary section reads as justified paragraphs rather than bullets.
#let paragraph-block(items) = {
  for item in items {
    par(justify: true, item)
    v(3pt)
  }
}

// Render one section only when it has content, so an empty section leaves no
// dangling heading.
#let render-section(section) = {
  if section.items.len() > 0 {
    section-heading(section.title)
    if section.kind == "summary" {
      paragraph-block(section.items)
    } else {
      bullet-list(section.items)
    }
  }
}

// The document entry point: page and text defaults, the header, then each section
// in document order.
#let resume(data) = {
  set document(author: data.full_name, title: data.full_name)
  set page(paper: "us-letter", margin: (x: 1.5cm, top: 1.3cm, bottom: 1.3cm))
  set text(font: _body-font, size: 10pt, lang: "en")
  set par(leading: 0.6em)

  header(data.full_name, data.contact, data.links)
  for section in data.sections {
    render-section(section)
  }
}
