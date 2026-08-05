interface StubPageProps {
  label: string;
}

export default function StubPage({ label }: StubPageProps) {
  return (
    <div className="stub-page">
      <h1>{label}</h1>
      <p className="stub-page__note">Not built yet — this page exists in the sidebar registry only.</p>
    </div>
  );
}
