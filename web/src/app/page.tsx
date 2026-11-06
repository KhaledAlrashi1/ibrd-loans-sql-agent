import { Ask } from "@/components/Ask";
import { DataPanel } from "@/components/DataPanel";
import { ThemeToggle } from "@/components/ThemeToggle";
import { longDate } from "@/lib/format";
import type { ExamplesFile } from "@/lib/types";
import examplesJson from "@/data/examples.json";

const examples = examplesJson as ExamplesFile;
const REPO_URL = "https://github.com/KhaledAlrashi1/ibrd-loans-sql-agent";
const LICENSE_URL = "https://creativecommons.org/licenses/by/4.0/";

export default function Home() {
  const ds = examples.dataset;
  return (
    <div className="wrap">
      <header className="top">
        <div className="top-bar">
          <ThemeToggle />
        </div>
        <h1>Ask the IBRD loan book</h1>
        <p className="lede">
          Ask a question in plain English. An AI model writes the SQL, the app checks it and runs it on the official
          data, and you see the answer, the SQL and every assumption behind it.
        </p>
        <p className="asof">
          Data as of {longDate(ds.end_of_period)} · {ds.rows.toLocaleString("en-US")} loans and guarantees
        </p>
      </header>

      <main>
        <Ask examples={examples} />
        <DataPanel dataset={ds} />
      </main>

      <footer className="foot">
        <p>Independent project, not affiliated with the World Bank.</p>
        <p>
          Data: World Bank, <a href={ds.source_url}>IBRD Statement of Loans and Guarantees ({ds.id})</a>,{" "}
          <a href={LICENSE_URL}>CC BY 4.0</a>. Snapshot of {longDate(ds.end_of_period)}; columns renamed and two
          derived flags added.
        </p>
        <p><a href={REPO_URL}>Code on GitHub</a></p>
      </footer>
    </div>
  );
}
