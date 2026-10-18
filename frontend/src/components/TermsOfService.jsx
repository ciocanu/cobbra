import { Link } from 'react-router-dom'
import { useConfig } from '../services/queries'

const SECTION = ({ title, children }) => (
  <section style={{ marginBottom: 32 }}>
    <h2 style={{ fontSize: 17, fontWeight: 700, color: 'var(--text-primary)', marginBottom: 12, borderBottom: '1px solid var(--border)', paddingBottom: 8 }}>{title}</h2>
    <div style={{ fontSize: 14, color: 'var(--text-secondary)', lineHeight: 1.75 }}>{children}</div>
  </section>
)

const P = ({ children }) => <p style={{ marginBottom: 12 }}>{children}</p>
const Li = ({ children }) => <li style={{ marginBottom: 6 }}>{children}</li>

export default function TermsOfService() {
  const { data: config } = useConfig()
  const paymentsOn = !!config?.payments_enabled
  return (
    <div style={{ maxWidth: 760, margin: '0 auto', padding: '48px 24px' }}>
      <Link to="/" style={{ color: 'var(--text-muted)', fontSize: 13, textDecoration: 'none', display: 'inline-flex', alignItems: 'center', gap: 6, marginBottom: 32 }}>
        ← Back
      </Link>

      <h1 style={{ fontSize: 28, fontWeight: 900, color: 'var(--text-primary)', marginBottom: 6 }}>Terms of Service</h1>
      <p style={{ color: 'var(--text-muted)', fontSize: 13, marginBottom: 40 }}>
        Last updated: 18 October 2026
      </p>

      <SECTION title="1. Acceptance of Terms">
        <P>By creating an account or using Cobbra, you agree to these Terms of Service. If you do not agree, do not use the service.</P>
      </SECTION>

      <SECTION title="2. Description of Service">
        <P>Cobbra is a cycling training and analytics platform. It allows you to upload cycling activities (GPX, FIT), view statistics, track segments, set goals, and generate AI-powered ride analysis and training plans.</P>
        {paymentsOn
          ? <P>Features are divided into a free tier (unlimited activity uploads, basic analytics) and paid tiers (Pro, Annual, Lifetime) unlocking AI analysis, data export, and training plans.</P>
          : <P>All features are free. AI ride analysis and training plans have a monthly limit per account, and AI features may be paused for everyone until the next month once the service's monthly AI budget is used up.</P>}
      </SECTION>

      <SECTION title="3. Account Registration">
        <ul style={{ paddingLeft: 20, marginBottom: 12 }}>
          <Li>You must be at least 16 years old to create an account.</Li>
          <Li>You are responsible for maintaining the confidentiality of your password.</Li>
          <Li>You must not impersonate others or create accounts on behalf of others without permission.</Li>
          <Li>You must provide accurate information where requested.</Li>
        </ul>
      </SECTION>

      <SECTION title="4. Acceptable Use">
        <P>You agree not to:</P>
        <ul style={{ paddingLeft: 20, marginBottom: 12 }}>
          <Li>Upload files that are not your own cycling activity data.</Li>
          <Li>Attempt to access other users' data or exploit security vulnerabilities.</Li>
          <Li>Use the service to transmit spam, malware, or harmful content.</Li>
          <Li>Write ride notes containing hate speech, harassment, threats, explicit sexual content, or content that encourages self-harm. Such notes will be flagged by automated content moderation and the activity may be rejected.</Li>
          <Li>Scrape the service or attempt to extract other users' data.</Li>
        </ul>
      </SECTION>

      <SECTION title="5. Intellectual Property">
        <P>Your activity data belongs to you. You grant us a limited licence to process and store it for the purpose of delivering the service.</P>
        <P>Cobbra's source code is published under an open-source licence; the licence in the project's repository sets what you may do with the code. The Cobbra name and logo are not covered by that licence.</P>
      </SECTION>

      {paymentsOn ? (
        <SECTION title="6. Payments and Subscriptions">
          <P>Paid plans are billed via Stripe. Prices are shown in euros (€) and include applicable taxes where required by law.</P>
          <P>Subscriptions (Pro, Annual) renew automatically until cancelled. You may cancel at any time; access continues until the end of the billing period. Lifetime plans are a one-time payment with no recurring charges.</P>
          <P>Refunds are handled on a case-by-case basis. Contact us within 14 days of purchase if you are unsatisfied.</P>
        </SECTION>
      ) : (
        <SECTION title="6. Price">
          <P>The service is free. There are no paid plans and no payment details are collected.</P>
        </SECTION>
      )}

      <SECTION title="7. Service Availability">
        <P>We aim to keep Cobbra available at all times but do not guarantee uninterrupted access. We may perform maintenance, updates, or take the service offline for operational reasons.</P>
        <P>We reserve the right to suspend or terminate accounts that violate these terms.</P>
      </SECTION>

      <SECTION title="8. Limitation of Liability">
        <P>Cobbra is provided "as is" without warranties of any kind. We are not liable for data loss, service interruptions, or any decisions made based on the statistics, AI analysis, or training plans generated by the service. Training recommendations are informational only and not a substitute for advice from a qualified coach or medical professional.</P>
        <P>Our total liability to you shall not exceed the amount paid by you for the service in the 12 months preceding the claim.</P>
      </SECTION>

      <SECTION title="9. Termination">
        <P>You may delete your account at any time from <strong style={{ color: 'var(--text-primary)' }}>Settings → Privacy &amp; Data</strong>. Deletion is immediate and irreversible.</P>
        <P>We may terminate accounts that breach these terms, with or without notice.</P>
      </SECTION>

      <SECTION title="10. Changes to Terms">
        <P>We may update these terms. Continued use of the service after changes are posted constitutes acceptance. We will notify you of significant changes via email where possible.</P>
      </SECTION>

      <SECTION title="11. Governing Law">
        <P>These terms are governed by applicable European Union law and the laws of the country in which the operator is established. Disputes shall be resolved in the competent courts of that jurisdiction.</P>
      </SECTION>

      <div style={{ marginTop: 48, paddingTop: 24, borderTop: '1px solid var(--border)', fontSize: 12, color: 'var(--text-muted)', display: 'flex', gap: 24 }}>
        <Link to="/privacy" style={{ color: 'var(--text-muted)', textDecoration: 'none' }}>Privacy Policy</Link>
        <Link to="/" style={{ color: 'var(--text-muted)', textDecoration: 'none' }}>← Home</Link>
      </div>
    </div>
  )
}
