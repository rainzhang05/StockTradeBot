const shellItems = [
  "FastAPI runtime skeleton",
  "SQLite bootstrap with Alembic",
  "CLI init, doctor, and status commands",
  "Frontend workspace and CI baseline"
];

export default function App() {
  return (
    <main style={styles.page}>
      <section style={styles.panel}>
        <p style={styles.eyebrow}>Phase 1</p>
        <h1 style={styles.heading}>StockTradeBot</h1>
        <p style={styles.copy}>
          Local-first runtime scaffolding is in place. Later phases will replace
          this placeholder with the operator dashboard.
        </p>
      </section>

      <section style={styles.panel}>
        <h2 style={styles.subheading}>Included in this scaffold</h2>
        <ul style={styles.list}>
          {shellItems.map((item) => (
            <li key={item}>{item}</li>
          ))}
        </ul>
      </section>
    </main>
  );
}

const styles: Record<string, React.CSSProperties> = {
  page: {
    minHeight: "100vh",
    margin: 0,
    padding: "48px 24px",
    backgroundColor: "#ffffff",
    color: "#111111",
    fontFamily: '"IBM Plex Mono", "Menlo", monospace'
  },
  panel: {
    maxWidth: "720px",
    margin: "0 auto 24px",
    padding: "24px",
    border: "1px solid #111111"
  },
  eyebrow: {
    margin: "0 0 8px",
    textTransform: "uppercase",
    letterSpacing: "0.12em",
    fontSize: "0.8rem"
  },
  heading: {
    margin: "0 0 12px",
    fontSize: "3rem"
  },
  subheading: {
    margin: "0 0 12px",
    fontSize: "1.25rem"
  },
  copy: {
    margin: 0,
    lineHeight: 1.6
  },
  list: {
    margin: 0,
    paddingLeft: "20px",
    lineHeight: 1.8
  }
};
