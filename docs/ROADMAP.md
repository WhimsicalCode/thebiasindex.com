# Roadmap

What we plan to improve. Each change to how pages are scored ships as a new methodology version, tested on the
benchmark first, with the results added to [`RESULTS.md`](RESULTS.md).

1. **Evidence behind every answer.** Show, next to each answer on every page, the sentence from the page that
   supports it and a one-line reason. Quotes are checked word for word against the page text, so a quote can't be
   made up. Some red flags are about something missing (no admitted weakness, no honest exit); those show the reason
   and say that nothing on the page was found.
2. **Suggest a company.** Anyone can propose a domain to be crawled, including their own, by opening an issue or a
   pull request that adds it to [`pipeline/domains.yml`](../pipeline/domains.yml). A new company is picked up by the
   next weekly run. Every company is crawled on the same weekly schedule, and that doesn't change on request.

Not planned: checking whether claims are true, and judging whether a comparison grades a competitor on things outside
its category. Both are listed as known gaps in [`METHODOLOGY.md`](METHODOLOGY.md).
