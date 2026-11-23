"""Integration test: loads sql/schema_v2.sql into a throwaway Postgres cluster and exercises constraints,
hybrid_search and claim_job. Skipped if Postgres server binaries or pgvector are not installed."""
import glob, os, pathlib, shutil, subprocess, tempfile, unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BIN = next(iter(sorted(glob.glob("/usr/lib/postgresql/*/bin"))[::-1]), None)
HAVE_VECTOR = bool(glob.glob("/usr/share/postgresql/*/extension/vector.control"))
PORT = "54329"


def as_pg(cmd):
    return (["runuser", "-u", "postgres", "--"] + cmd) if os.geteuid() == 0 else cmd


def onehot(i, n=768):
    return "[" + ",".join("1" if j == i else "0" for j in range(n)) + "]"


@unittest.skipUnless(BIN and HAVE_VECTOR, "needs Postgres server + pgvector")
class SchemaTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        shutil.chown(cls.dir, "postgres") if os.geteuid() == 0 else None
        os.chmod(cls.dir, 0o755)
        subprocess.run(as_pg([f"{BIN}/initdb", "-D", f"{cls.dir}/data", "-A", "trust", "-U", "postgres"]), check=True, capture_output=True)
        subprocess.run(as_pg([f"{BIN}/pg_ctl", "-D", f"{cls.dir}/data", "-o", f"-p {PORT} -k {cls.dir} -c listen_addresses=''",
                              "-l", f"{cls.dir}/log", "-w", "start"]), check=True, capture_output=True)
        cls.sql("create database rb")
        r = cls.psql(["-f", "-"], stdin=(ROOT / "sql/schema_v2.sql").read_text())   # via stdin: the postgres OS user may not be able to read this folder
        assert r.returncode == 0, r.stderr
        cls.ins()

    @classmethod
    def tearDownClass(cls):
        subprocess.run(as_pg([f"{BIN}/pg_ctl", "-D", f"{cls.dir}/data", "-m", "immediate", "-w", "stop"]), capture_output=True)
        shutil.rmtree(cls.dir, ignore_errors=True)

    @classmethod
    def psql(cls, args, db="rb", stdin=None):
        return subprocess.run(as_pg(["psql", "-h", cls.dir, "-p", PORT, "-U", "postgres", "-d", db, "-v", "ON_ERROR_STOP=1", "-At"] + args),
                              capture_output=True, text=True, cwd="/", input=stdin)

    @classmethod
    def sql(cls, q, db="postgres"):
        return cls.psql(["-c", q], db=db)

    @classmethod
    def ins(cls):
        q = f"""
        insert into sources (id, canonical_url, kind) values ('00000000-0000-0000-0000-0000000000a1','https://instagram.com/reel/AAA/','reel');
        insert into evidence (id, source_id, modality, slide_index, verbatim, method, pipeline_version)
          values ('00000000-0000-0000-0000-0000000000e1','00000000-0000-0000-0000-0000000000a1','on_screen',6,'github.com/onyx-dot-app/onyx','tesseract','t');
        insert into resources (id, source_id, primary_evidence_id, name, kind, observed)
          values ('00000000-0000-0000-0000-0000000000b1','00000000-0000-0000-0000-0000000000a1','00000000-0000-0000-0000-0000000000e1','Onyx','github_repo','github.com/onyx-dot-app/onyx');
        insert into chunks (source_id, resource_id, content, embedding) values
          ('00000000-0000-0000-0000-0000000000a1','00000000-0000-0000-0000-0000000000b1','Onyx onyx-dot-app/onyx open source enterprise search over your company docs','{onehot(1)}'),
          ('00000000-0000-0000-0000-0000000000a1',null,'Scrapling adaptive web scraping library that survives site redesigns','{onehot(2)}'),
          ('00000000-0000-0000-0000-0000000000a1',null,'Comment REPOS to receive the list of ten GitHub repositories in DM','{onehot(3)}');
        insert into jobs (stage, priority, idempotency_key) values ('understand', 9, 'k-low'), ('understand', 1, 'k-high'), ('verify', 1, 'k-other');
        """
        r = cls.psql(["-c", q])
        assert r.returncode == 0, r.stderr

    def test_level_requires_verification(self):
        r = self.sql("update resources set evidence_level='exists' where id='00000000-0000-0000-0000-0000000000b1'", "rb")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("level_needs_verification", r.stderr)
        ok = self.sql("update resources set evidence_level='exists', verification_status='verified' where id='00000000-0000-0000-0000-0000000000b1'", "rb")
        self.assertEqual(ok.returncode, 0, ok.stderr)

    def test_resource_needs_evidence(self):
        r = self.sql("insert into resources (source_id, name, kind, observed) values ('00000000-0000-0000-0000-0000000000a1','x','other','x')", "rb")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("primary_evidence_id", r.stderr)

    def test_duplicate_source_url_blocked(self):
        r = self.sql("insert into sources (canonical_url, kind) values ('https://instagram.com/reel/AAA/','reel')", "rb")
        self.assertNotEqual(r.returncode, 0)

    def top(self, q, emb=None):
        e = f"'{emb}'::vector" if emb else "null"
        r = self.psql(["-F", "|", "-c", f"select left(content,12), lanes from hybrid_search('{q}', {e}, 3)"])
        self.assertEqual(r.returncode, 0, r.stderr)
        return [ln.split("|") for ln in r.stdout.strip().splitlines()]

    def test_exact_lane_finds_repo_string_without_embedding(self):
        rows = self.top("onyx-dot-app/onyx")
        self.assertEqual(rows[0][0], "Onyx onyx-do")
        self.assertIn("exact", rows[0][1])

    def test_fulltext_lane(self):
        rows = self.top("web scraping library")   # 'simple' config: no stemming on purpose (Hindi/Hinglish safe)
        self.assertTrue(rows[0][0].startswith("Scrapling"))
        self.assertIn("fulltext", rows[0][1])

    def test_vector_lane_and_fusion(self):
        rows = self.top("something unrelated in words", onehot(3))
        self.assertTrue(rows[0][0].startswith("Comment REPO"))
        self.assertIn("vector", rows[0][1])
        fused = self.top("onyx-dot-app/onyx", onehot(1))       # exact + vector agree -> both lanes recorded (full-text may join too)
        self.assertIn("exact", fused[0][1]); self.assertIn("vector", fused[0][1])

    def test_like_wildcards_are_escaped(self):
        self.assertEqual(self.psql(["-c", "select count(*) from hybrid_search('100%_off')"]).stdout.strip(), "0")

    def test_claim_job_priority_and_exhaustion(self):
        def claim():
            r = self.psql(["-c", "select idempotency_key, state, attempts from claim_job('understand')"])
            self.assertEqual(r.returncode, 0, r.stderr)
            return r.stdout.strip()
        self.assertEqual(claim(), "k-high|running|1")
        self.assertEqual(claim(), "k-low|running|1")
        self.assertEqual(claim(), "||")                          # nothing left for this stage; 'verify' job untouched
        left = self.psql(["-c", "select count(*) from jobs where state='queued'"]).stdout.strip()
        self.assertEqual(left, "1")


if __name__ == "__main__":
    unittest.main()
