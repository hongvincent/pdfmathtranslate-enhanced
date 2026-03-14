export function MetricCard(props: {
  label: string;
  value: string;
  hint: string;
}) {
  const { label, value, hint } = props;

  return (
    <article className="metric-card">
      <span className="eyebrow">{label}</span>
      <strong>{value}</strong>
      <p>{hint}</p>
    </article>
  );
}
