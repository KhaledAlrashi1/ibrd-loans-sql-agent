import { Ask } from "@/components/Ask";
import { DataPanel } from "@/components/DataPanel";
import { RegionChart } from "@/components/RegionChart";
import { Stats } from "@/components/Stats";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Trust } from "@/components/Trust";
import type { ExamplesFile, Stats as StatsFile } from "@/lib/types";
import examplesJson from "@/data/examples.json";
import statsJson from "@/data/stats.json";

const examples = examplesJson as ExamplesFile;
const stats = statsJson as StatsFile;
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
          Ask in plain English. An AI writes the SQL, the app checks and runs it, and you see the SQL and every
          assumption.
        </p>
        <Stats stats={stats} />
      </header>

      <main>
        <Ask examples={examples} />
        <RegionChart regions={stats.outstanding_by_region} endOfPeriod={stats.end_of_period} />
        <Trust repoUrl={REPO_URL} />
        <DataPanel endOfPeriod={ds.end_of_period} />
      </main>

      <footer className="foot">
        <p>
          Data: World Bank, <a href={ds.source_url}>IBRD Statement of Loans and Guarantees</a>,{" "}
          <a href={LICENSE_URL}>CC BY 4.0</a>; columns renamed, two flags derived. Not affiliated with the World Bank.
        </p>
        <p><a href={REPO_URL}>Code on GitHub</a></p>
      </footer>
    </div>
  );
}
