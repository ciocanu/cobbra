import { Link } from 'react-router-dom'

const SECTION = ({ title, children }) => (
  <section style={{ marginBottom: 32 }}>
    <h2 style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12, borderBottom: '1px solid var(--border)', paddingBottom: 8 }}>{title}</h2>
    <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.75 }}>{children}</div>
  </section>
)

const P = ({ children }) => <p style={{ marginBottom: 12 }}>{children}</p>
const Li = ({ children }) => <li style={{ marginBottom: 6 }}>{children}</li>

export default function PrivacyPolicy() {
  return (
    <div style={{ maxWidth: 760, margin: '0 auto', padding: '48px 24px' }}>
      <Link to="/" style={{ color: 'var(--text-muted)', fontSize: 13, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 32 }}>
        ← Back
      </Link>

      <h1 style={{ fontSize: 28, fontWeight: 900, color: 'var(--text-primary)', marginBottom: 6 }}>Privacy Policy</h1>
      <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 40 }}>
        Last updated: {new Date().toLocaleDateString('en-GB', { day: 'numeric', month: 'long', year: 'numeric' })}
      </p>

      <SECTION title="1. Who we are">
        <P>Cobbra is a cycling training and analytics application operated as a sole-trader service. When this policy refers to "we", "us", or "our", it means the operator of Cobbra.</P>
        <P><strong style={{ color: 'var(--text-primary)' }}>Contact for data protection matters:</strong> You can reach us via the Settings page inside the app, or by replying to any transactional email you have received from Cobbra. We will respond to all data-related requests within 30 days as required by GDPR Art. 12(3).</P>
      </SECTION>

      <SECTION title="2. What data we collect">
        <P><strong style={{ color: 'var(--text-primary)' }}>Account data:</strong> Username, email address (optional), hashed password, membership tier, and account creation date.</P>
        <P><strong style={{ color: 'var(--text-primary)' }}>Fitness profile:</strong> Age, body weight, maximum heart rate, resting heart rate, FTP (functional threshold power), experience level, and bike type — all entered voluntarily by you in Settings.</P>
        <P><strong style={{ color: 'var(--text-primary)' }}>Activity data:</strong> When you upload a ride (GPX or FIT file) or sync from Strava, we store the full GPS track (latitude, longitude, timestamp, elevation per second), along with heart rate, cadence, speed, power, and distance. We also store derived metrics such as average speed, suffer score, elevation gain, TSS, and any ride notes you write.</P>
        <P><strong style={{ color: 'var(--text-primary)' }}>Segment data:</strong> GPS coordinates of start and end points of any segments you create.</P>
        <P><strong style={{ color: 'var(--text-primary)' }}>Payment data:</strong> Stripe customer ID and subscription dates. We do not store credit card numbers — all payment processing is handled by Stripe.</P>
        <P><strong style={{ color: 'var(--text-primary)' }}>Technical data:</strong> IP address (used only for rate-limiting login/registration attempts and automatically deleted after 2 hours).</P>
      </SECTION>

      <SECTION title="3. How we use your data">
        <ul style={{ paddingLeft: 20, marginBottom: 12 }}>
          <Li>To provide the service: display your rides, compute statistics, and generate personalised training plans.</Li>
          <Li>To send transactional emails: email verification and (optionally) promotional offers you have explicitly opted into.</Li>
          <Li>To process payments via Stripe for paid plans.</Li>
          <Li>To generate AI ride analysis via Anthropic Claude (see Section 5).</Li>
          <Li>To automatically retrieve weather conditions at the start of each ride from Open-Meteo.</Li>
        </ul>
        <P>We do not sell your data. We do not use your data for advertising.</P>
      </SECTION>

      <SECTION title="4. Legal basis for processing (GDPR)">
        <ul style={{ paddingLeft: 20, marginBottom: 12 }}>
          <Li><strong style={{ color: 'var(--text-primary)' }}>Contract performance (Art. 6(1)(b)):</strong> Processing necessary to deliver the service you signed up for — storing rides, computing stats, managing your account.</Li>
          <Li><strong style={{ color: 'var(--text-primary)' }}>Legitimate interests (Art. 6(1)(f)):</strong> Rate-limiting IP tracking to protect the service from abuse. Our interest in securing the platform does not override your rights given the minimal nature of this processing (IPs deleted within 2 hours).</Li>
          <Li><strong style={{ color: 'var(--text-primary)' }}>Consent (Art. 6(1)(a)):</strong> AI analysis of your ride data — you trigger this explicitly by clicking "Analyse Ride". You may withdraw this consent at any time by not using this feature; past analyses can be cleared from the activity page.</Li>
        </ul>
      </SECTION>

      <SECTION title="5. Third-party processors and international transfers">
        <P>We share data with the following processors, each bound by their own data processing agreements and privacy policies. Where a processor is located outside the European Economic Area (EEA), transfers are made on the basis of Standard Contractual Clauses (SCCs) adopted by the European Commission, or an EU adequacy decision.</P>
        <ul style={{ paddingLeft: 20, marginBottom: 12 }}>
          <Li>
            <strong style={{ color: 'var(--text-primary)' }}>Anthropic (Claude AI) — United States:</strong> When you click "Analyse Ride", your activity's summary metrics (speed, heart rate, elevation, cadence, power, weather, VAM, HR decoupling) are sent to Anthropic's API to generate a coach-style analysis. No raw GPS coordinates are sent. Your ride notes are also sent to Claude for automated content moderation (to detect prohibited content) each time you save a note. No data is retained by Anthropic beyond the API call. Transfer basis: Standard Contractual Clauses.
          </Li>
          <Li>
            <strong style={{ color: 'var(--text-primary)' }}>Stripe — United States:</strong> Your email address and a Stripe customer ID are used to process subscription payments. Stripe is PCI DSS compliant and handles all card data directly. Transfer basis: Standard Contractual Clauses / EU adequacy decision.
          </Li>
          <Li>
            <strong style={{ color: 'var(--text-primary)' }}>Strava — United States:</strong> If you connect Strava, we receive an OAuth access token and use it to import your cycling activities. We store only activity data, not your Strava profile beyond the athlete ID. Transfer basis: Standard Contractual Clauses.
          </Li>
          <Li>
            <strong style={{ color: 'var(--text-primary)' }}>Open-Meteo — European Union:</strong> The GPS coordinates of the first point of each uploaded ride (latitude and longitude) along with the ride date are sent to Open-Meteo to retrieve historical weather conditions. Open-Meteo is open-source, hosted in the EU, requires no account, and does not store personal data. No international transfer.
          </Li>
        </ul>
      </SECTION>

      <SECTION title="6. Data retention">
        <P>Your data is kept for as long as your account exists. You can delete your account at any time from <strong style={{ color: 'var(--text-primary)' }}>Settings → Privacy &amp; Data</strong>, which permanently and irreversibly erases all personal data including activities, track points, goals, segments, and your profile.</P>
        <P>Rate-limit IP records are automatically purged within 2 hours of creation.</P>
      </SECTION>

      <SECTION title="7. Your rights (GDPR Art. 15–22)">
        <P>If you are in the EU or EEA, you have the following rights. To exercise any right, contact us via Settings or email. We will respond within 30 days at no charge.</P>
        <ul style={{ paddingLeft: 20, marginBottom: 12 }}>
          <Li><strong style={{ color: 'var(--text-primary)' }}>Access (Art. 15):</strong> Request a copy of the personal data we hold about you.</Li>
          <Li><strong style={{ color: 'var(--text-primary)' }}>Portability (Art. 20):</strong> Download all your data in machine-readable JSON format from <strong>Settings → Privacy &amp; Data → Download My Data</strong>. The export includes your profile, all activity metadata, ride notes, AI analysis results, personal records, goals, segments, and training plans. Raw GPS track data can be exported per-activity via the CSV or GPX buttons on each activity page.</Li>
          <Li><strong style={{ color: 'var(--text-primary)' }}>Erasure (Art. 17):</strong> Delete your account and all associated data from <strong>Settings → Privacy &amp; Data → Delete Account</strong>. Deletion is immediate and irreversible.</Li>
          <Li><strong style={{ color: 'var(--text-primary)' }}>Rectification (Art. 16):</strong> Update your email, fitness profile, and other data at any time in Settings.</Li>
          <Li><strong style={{ color: 'var(--text-primary)' }}>Restriction of processing (Art. 18):</strong> Request that we restrict how we use your data (e.g. while a dispute is being resolved). Contact us to exercise this right.</Li>
          <Li><strong style={{ color: 'var(--text-primary)' }}>Objection (Art. 21):</strong> Object to processing based on legitimate interests. Contact us and we will cease that processing unless we can demonstrate compelling legitimate grounds.</Li>
          <Li><strong style={{ color: 'var(--text-primary)' }}>Withdraw consent (Art. 7(3)):</strong> Where processing is based on your consent (AI ride analysis), you may withdraw it at any time without affecting the lawfulness of prior processing. Simply stop using the "Analyse Ride" feature.</Li>
          <Li><strong style={{ color: 'var(--text-primary)' }}>Lodge a complaint (Art. 77):</strong> You have the right to lodge a complaint with the data protection supervisory authority in your EU member state. In Portugal: <strong>Comissão Nacional de Proteção de Dados (CNPD)</strong> — cnpd.pt. In other EU countries, contact your national DPA.</Li>
        </ul>
      </SECTION>

      <SECTION title="8. Security">
        <P>Passwords are stored as salted cryptographic hashes and are never readable. Authentication uses short-lived, HttpOnly, SameSite=Strict cookies. All connections are encrypted in transit via HTTPS in production.</P>
      </SECTION>

      <SECTION title="9. Data breach notification">
        <P>In the event of a personal data breach that is likely to result in a risk to your rights and freedoms, we will notify the competent supervisory authority within 72 hours of becoming aware of the breach, as required by Art. 33 GDPR. Where the breach is likely to result in a high risk to you, we will also notify you directly without undue delay (Art. 34 GDPR).</P>
      </SECTION>

      <SECTION title="10. Changes to this policy">
        <P>We may update this policy. Significant changes will be communicated via the email address on your account. The date at the top of this page reflects the most recent revision. Continued use of the service after changes are posted constitutes acceptance of the updated policy.</P>
      </SECTION>

      <div style={{ marginTop: 48, paddingTop: 24, borderTop: '1px solid var(--border)', fontSize: 12, color: 'var(--text-muted)', display: 'flex', gap: 24 }}>
        <Link to="/terms" style={{ color: 'var(--text-muted)', textDecoration: 'none' }}>Terms of Service</Link>
        <Link to="/" style={{ color: 'var(--text-muted)', textDecoration: 'none' }}>← Home</Link>
      </div>
    </div>
  )
}
