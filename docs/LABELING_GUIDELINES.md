# thebiasindex.com benchmark: labeling guidelines (methodology v8)

Why the questions are what they are, and how they fit together: `../METHODOLOGY.md`.

These rules decide the gold labels. Luna is scored against them, so they are written before any Luna output
for the benchmark pages is looked at, and they're published with the gold set.

Label from the extracted page text (what Luna sees), not from the rendered page. A label of `null` means
"does not apply": the page isn't a `competitor_comparison`.

## Publisher's product

Any product in the company's `product_names` (`domains.yml`). Lucidchart, Lucidspark and Lucidscale are all
Lucid's products; ClickUp's page about Notion compares ClickUp with a rival.

## Page type

| Type | Rule |
|---|---|
| `competitor_comparison` | Compares the publisher's product with one or more named rival products, **or** lists alternatives to a product (a rival or the publisher's own) **and the publisher's product is among them**. Roundups ("best AI research tools") that include the publisher's product count too. |
| `third_party_comparison` | Compares or lists named products, **none of them the publisher's**. A closing call to action for the publisher's product doesn't change this, as long as the product isn't one of the options compared. |
| `own_products` | Compares the publisher's own plans, editions or storage options. |
| `educational` | Compares concepts, methods or roles, not products (`kanban-vs-scrum`, `revenue-vs-sales`). |
| `hub` | An index linking to comparison pages, with no real comparison of its own. |
| `other` | Anything else: blog posts that only mention a "vs", contact forms, survey results. |

## The five questions (competitor comparisons only)

Yes is always the red flag.

1. **Best at everything:** Does the page present the publisher's product as winning or tying on everything it
   compares, conceding no area where a named competitor is stronger?
   (v1-v5 asked "Crowns itself: does the page present the publisher's product as the best choice overall?".
   Replaced in v6: every vendor page claims to be better at something; the red flag is conceding nothing.)
   - **No** (fair) if the page states, and leaves standing, at least one **area** where a named competitor is
     stronger than the publisher's product: a feature, capability, price or free plan, platform, integration,
     ease of use, scale or ecosystem. Examples: "Xmind offers a broader diagramming toolkit", "Bolt.new wins on
     prototyping speed", "SciSpace is the stronger choice for understanding individual papers", "draw.io is free
     and ideal for teams on a budget", "FigJam: native tie-in with Figma design files", a table row the
     competitor wins.
   - **Yes** (red flag) if the publisher wins or ties on every point the page makes, or every concession is
     taken back in the same breath ("Mural may work for brainstorming, but it's no match for Lucidspark").
   - The concession must be against the **publisher's** product. On a Wrike page about ClickUp vs Monday,
     "Monday is more intuitive than ClickUp" concedes nothing to Wrike.
   - Ties ("both offer real-time collaboration") and generic praise of a rival ("Miro is a popular tool")
     are not concessions. A "Best for X" label on a rival counts when X names a capability or platform the
     rival is stronger at ("Best for teams on Apple devices"), not when it only names an audience.
   - **No** for a page that compares a single specific feature and makes no claim beyond it ("Gliffy vs draw.io:
     concurrent editing"). Winning the one thing a page is about isn't claiming to win everything.
   - This question is about **what** the competitor does better; question 2 is about **who** should pick
     it. They often agree, but not always.
2. **No honest exit:** Does the page leave out every situation where a competitor would be the better
   choice?
   - An exit is a **concrete** situation, team or use case where a named competitor is the better or right
     choice, and it's left standing ("choose Obsidian if you want local Markdown files").
   - "Ideal for teams that need X" about a listed rival counts, unless it's immediately undercut ("…but
     Miro does that too").
   - Generic hedges ("every team is different", "it depends on your needs") are not exits.
3. **No admitted weakness:** Does the page avoid saying anything the publisher's own product can't do or does
   poorly? (v1-v7 called this "Defused drawbacks"; the rule is unchanged, the boundary with question 1 is now
   explicit.)
   - **No** (fair) if you can quote the page saying, about the publisher's product, what it can't do, doesn't
     include, or does poorly, and the statement is left standing: "Ponder is not a screening tool", "Framer
     does not provide a self-hostable HTML export", "native design tokens (coming soon)", a "Cons" or
     "Limitations" list, a table cell where the publisher has "No" or "Limited".
   - **Yes** (red flag) if there is no such sentence, or every one is rebutted in the same breath ("can be
     overwhelming. That said, our intuitive interface…").
   - **Doesn't count:** a weakness only implied by praising a competitor ("Choose XMind if you want more
     structures"). That is credit to the competitor and belongs to question 1. Plan or pricing descriptions ("the
     free plan includes 3 boards") don't count either, unless the page itself calls them a limitation.
4. **Vague attacks:** Are the page's criticisms of competitors vague, with no specifics, numbers or
   sources?
   - **Yes** if most criticisms are unfalsifiable ("limited customization", "lacks some collaboration
     features", "outdated", "hard to use").
   - **No** if most name something checkable (a missing feature, a price, a limit, a source), **or if the
     page doesn't criticize competitors at all**.
5. **Uneven scrutiny:** Does the page list clearly more drawbacks for competitors than for the publisher's
   product?
   - **Yes** if competitors get clearly more or harsher drawbacks, including when the publisher's product
     gets none and competitors get some.
   - **No** if drawbacks are roughly balanced, or neither side gets any.

## Recording a label

One JSON line per page in `gold.jsonl`: page type, the five answers (`true`, `false` or `null`), a
one-line reason per answer that quotes the page where possible, the labeler, and `needs_human: true` when
the call was close. Human reviewers overwrite the labeler field with their name when they change or confirm
a label.
