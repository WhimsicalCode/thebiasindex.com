// npm run pull-db: replace the local database with the one from the latest weekly release, the data the live site
// is built from. The file we had is kept as bias_index.previous.sqlite, and a download that doesn't open as a
// database with a finished run never replaces it.
import { existsSync, renameSync, rmSync } from "node:fs"
import { writeFile } from "node:fs/promises"
import path from "node:path"
import { DatabaseSync } from "node:sqlite"

const RELEASE_URL =
  "https://github.com/WhimsicalCode/thebiasindex.com/releases/latest/download/bias_index.sqlite"

const dbFile =
  process.env.BIAS_INDEX_DB ??
  path.resolve(import.meta.dirname, "..", "..", "data", "bias_index.sqlite")
const download = `${dbFile}.download`
const previous = dbFile.replace(/\.sqlite$/, ".previous.sqlite")

/** When the latest finished run in a database started, e.g. "2026-11-22T06:00:00Z". */
function lastRun(file: string): string | undefined {
  const db = new DatabaseSync(file, { readOnly: true })
  try {
    const row = db
      .prepare(
        "select started_at from runs where finished_at is not null order by run_id desc limit 1"
      )
      .get() as { started_at: string } | undefined
    return row?.started_at
  } finally {
    db.close()
  }
}

const before = existsSync(dbFile) ? lastRun(dbFile) : undefined
console.log(`Now: ${before ?? "no database"} (${dbFile})`)

console.log(`Downloading ${RELEASE_URL}`)
const response = await fetch(RELEASE_URL)
if (!response.ok) throw new Error(`Download failed: ${response.status} ${response.statusText}`)
await writeFile(download, new Uint8Array(await response.arrayBuffer()))

let after: string | undefined
try {
  after = lastRun(download)
} catch (error) {
  rmSync(download)
  throw new Error(`The download isn't a database we can read: ${error}`)
}
if (!after) {
  rmSync(download)
  throw new Error("The download has no finished run, so we kept the database we had.")
}

if (after === before) {
  rmSync(download)
  console.log(`Already the latest run: ${after}`)
} else {
  if (existsSync(dbFile)) renameSync(dbFile, previous)
  renameSync(download, dbFile)
  console.log(`Updated to the run of ${after}. The old database is in ${previous}`)
}
