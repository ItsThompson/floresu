// Entry point for the Floresu "Classic" template.
//
// The render module passes the resolved resume document as a JSON string on
// sys.inputs.data (never as Typst source). Here it is decoded to a dictionary and
// handed to the template; user text is therefore always content, never markup.

#import "template.typ": resume

#let data = json(bytes(sys.inputs.data))

#resume(data)
