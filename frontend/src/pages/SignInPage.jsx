import { useState } from 'react';
import { Link, Navigate, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { BrandMark, Icon } from '../components/Icon';
import { errorMessage } from '../components/ui';

export const homeFor = (user) => (user?.role === 'admin' ? '/admin/dashboard' : '/employee/dashboard');
export const loginFor = (role) => (role === 'admin' ? '/admin/login' : '/employee/login');

// Two separate portals, each with its own address, look and wording. Each accepts only its own kind of account.
const PORTALS = {
  employee: {
    role: 'employee',
    title: 'Employee sign-in',
    lead: 'Submit medical bills and follow your claims.',
    headline: 'Medical bills, checked against your policy in seconds.',
    pitch: 'Upload a hospital bill and it is read, matched to your reimbursement policy and decided. Anything unusual goes to a reviewer, with the policy clause that applies.',
    other: { to: '/admin/login', text: 'Claims reviewer?', link: 'Use the reviewer sign-in' },
    wrongRole: 'This is a reviewer account. Sign in on the reviewer page instead:',
  },
  admin: {
    role: 'admin',
    title: 'Reviewer sign-in',
    lead: 'For claims reviewers and administrators.',
    headline: 'Every flagged claim, with the evidence to decide it.',
    pitch: 'Review the claims the automatic checks couldn’t settle: the red flags, the policy clause, the extracted bill details and every processing step, side by side.',
    other: { to: '/employee/login', text: 'Submitting a bill?', link: 'Use the employee sign-in' },
    wrongRole: 'This is an employee account. Sign in on the employee page instead:',
  },
};

/** The specimen bill on the sign-in page: what each portal is for, shown rather than described. */
function SpecimenBill({ portal }) {
  const review = portal === 'admin';
  return (
    <figure className="specimen" aria-hidden="true">
      <div className="specimen__paper">
        <div className="specimen__head">
          <strong>{review ? 'Apollo Hospital' : 'City Care Dental Clinic'}</strong>
          <span>{review ? 'Invoice INV-90017' : 'Invoice INV-70421'}</span>
        </div>
        <dl className="specimen__lines">
          <div><dt>Root canal treatment</dt><dd>{review ? '4,800.00' : '5,500.00'}</dd></div>
          <div><dt>Dental X-ray</dt><dd>{review ? '700.00' : '800.00'}</dd></div>
          <div><dt>Consultation</dt><dd>{review ? '500.00' : '700.00'}</dd></div>
        </dl>
        <div className="specimen__total"><span>Total</span><span>{review ? '₹6,000.00' : '₹7,000.00'}</span></div>
        {review ? (
          <span className="stamp stamp--review specimen__stamp"><span className="stamp__label">Needs review</span></span>
        ) : (
          <span className="stamp stamp--approved specimen__stamp">
            <span className="stamp__label">Approved</span><span className="stamp__amount">₹7,000</span>
          </span>
        )}
      </div>
      <figcaption className="specimen__note">
        {review
          ? 'Flagged: the patient on the bill isn’t the employee who submitted it'
          : 'Checked against the Dental Care policy, limit ₹15,000 a year'}
      </figcaption>
    </figure>
  );
}

export function SignInPage({ portal = 'employee' }) {
  const copy = PORTALS[portal] || PORTALS.employee;
  const navigate = useNavigate();
  const { user, loading, signIn, signOut } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [wrongPortal, setWrongPortal] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user && user.role === copy.role) return <Navigate to={homeFor(user)} replace />;

  const onSubmit = async (event) => {
    event.preventDefault();
    setError('');
    setWrongPortal(false);
    if (!email.trim() || !password) {
      setError('Enter your work email and password.');
      return;
    }
    setSubmitting(true);
    try {
      const signedIn = await signIn(email.trim(), password);
      if (signedIn.role !== copy.role) {
        signOut();
        setWrongPortal(true);
        setError(copy.wrongRole);
        setSubmitting(false);
        return;
      }
      navigate(homeFor(signedIn), { replace: true });
    } catch (signInError) {
      const status = signInError.response?.status;
      setError(status === 401 ? 'That email and password don’t match an account.' : errorMessage(signInError));
      setSubmitting(false);
    }
  };

  return (
    <div className={`signin signin--${portal}`}>
      <section className="signin__story">
        <div className="signin__brand">
          <BrandMark size={34} /><span>Medical Claim AI</span>
          {portal === 'admin' ? <span className="signin__portal-tag">Reviewer portal</span> : null}
        </div>
        <div className="signin__pitch">
          <h1>{copy.headline}</h1>
          <p>{copy.pitch}</p>
        </div>
        <SpecimenBill portal={portal} />
      </section>

      <section className="signin__form-side">
        <form className="signin__form" onSubmit={onSubmit} noValidate>
          <h2>{copy.title}</h2>
          <p className="signin__lead">{copy.lead}</p>

          <label className="field">
            <span className="field__label">Work email</span>
            <input type="email" autoComplete="username" value={email} required autoFocus
              onChange={(event) => setEmail(event.target.value)} />
          </label>
          <label className="field">
            <span className="field__label">Password</span>
            <input type="password" autoComplete="current-password" value={password} required
              onChange={(event) => setPassword(event.target.value)} />
          </label>

          {error ? (
            <p className="form-error" role="alert">
              <Icon name="alert" size={16} />
              <span>{error}{wrongPortal ? <> <Link to={copy.other.to}>{copy.other.link.replace('Use the ', '')}</Link></> : null}</span>
            </p>
          ) : null}

          <button type="submit" className="button button--primary button--block" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
          <p className="signin__help">No account yet? Your administrator creates one for you.</p>
          <p className="signin__switch">{copy.other.text} <Link to={copy.other.to}>{copy.other.link}</Link></p>
        </form>
      </section>
    </div>
  );
}
