// Anything with data-question (bar segments in flag-bar and flag-split, the answer dots on company pages) shows its
// question on hover: colour, label, a value ("1,536 red flags", "Red flag"…) and the question in full. The bars
// clip their segments to round their corners, so one tooltip follows the pointer instead of living inside them.
// On touch screens a tap shows it too, unless the element is part of a link (a tap on a ranking row opens it).
const tip = document.createElement("div")
tip.className = "seg-tip"
tip.hidden = true
document.body.append(tip)

function show(target: HTMLElement, x: number, y: number) {
  const { label, value, question, color } = target.dataset
  const title = document.createElement("b")
  const dot = document.createElement("i")
  dot.style.background = color ?? ""
  title.append(dot, label ?? "")
  const detail = document.createElement("span")
  detail.textContent = value ?? ""
  const text = document.createElement("small")
  text.textContent = question ?? ""
  tip.replaceChildren(title, detail, text)
  tip.hidden = false
  // Above the pointer, kept inside the window.
  const { width, height } = tip.getBoundingClientRect()
  const left = Math.min(Math.max(8, x - width / 2), window.innerWidth - width - 8)
  const top = y - height - 14
  tip.style.transform = `translate(${left}px, ${top < 8 ? y + 20 : top}px)`
}

const questionAt = (target: EventTarget | null) =>
  target instanceof Element ? target.closest<HTMLElement>("[data-question]") : null

document.addEventListener("pointermove", event => {
  if (event.pointerType !== "mouse") return
  const target = questionAt(event.target)
  if (target) show(target, event.clientX, event.clientY)
  else tip.hidden = true
})
document.addEventListener("click", event => {
  const target = questionAt(event.target)
  if (target && !target.closest("a") && !matchMedia("(hover: hover)").matches)
    show(target, event.clientX, event.clientY)
  else if (!target) tip.hidden = true
})
document.addEventListener("scroll", () => (tip.hidden = true), { passive: true })
