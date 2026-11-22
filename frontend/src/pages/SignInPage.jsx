import { useState } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';
import { BrandMark, Icon } from '../components/Icon';
import { errorMessage } from '../components/ui';

export const homeFor = (user) => (user?.role === 'admin' ? '/admin/dashboard' : '/employee/dashboard');

/** The specimen bill on the sign-in page: what the product does, shown rather than described. */
function SpecimenBill() {
  return (
    <figure className="specimen" aria-hidden="true">
      <div className="specimen__paper">
        <div className="specimen__head">
          <strong>City Care Dental Clinic</strong>
          <span>Invoice INV-70421</span>
        </div>
        <dl className="specimen__lines">
          <div><dt>Root canal treatment</dt><dd>5,500.00</dd></div>
          <div><dt>Dental X-ray</dt><dd>800.00</dd></div>
          <div><dt>Consultation</dt><dd>700.00</dd></div>
        </dl>
        <div className="specimen__total"><span>Total</span><span>₹7,000.00</span></div>
        <span className="stamp stamp--approved specimen__stamp">
          <span className="stamp__label">Approved</span><span className="stamp__amount">₹7,000</span>
        </span>
      </div>
      <figcaption className="specimen__note">
        Checked against the Dental Care policy, limit ₹15,000 a year
      </figcaption>
    </figure>
  );
}

export function SignInPage() {
  const navigate = useNavigate();
  const { user, loading, signIn } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  if (!loading && user) return <Navigate to={homeFor(user)} replace />;

  const onSubmit = async (event) => {
    event.preventDefault();
    setError('');
    if (!email.trim() || !password) {
      setError('Enter your work email and password.');
      return;
    }
    setSubmitting(true);
    try {
      const signedIn = await signIn(email.trim(), password);
      navigate(homeFor(signedIn), { replace: true });
    } catch (signInError) {
      const status = signInError.response?.status;
      setError(status === 401 ? 'That email and password don’t match an account.' : errorMessage(signInError));
      setSubmitting(false);
    }
  };

  return (
    <div className="signin">
      <section className="signin__story">
        <div className="signin__brand"><BrandMark size={34} /><span>Medical Claim AI</span></div>
        <div className="signin__pitch">
          <h1>Medical bills, checked against your policy in seconds.</h1>
          <p>
            Upload a hospital bill and it is read, matched to the reimbursement policy and decided. Anything unusual
            goes to a reviewer, with the policy clause that applies.
          </p>
        </div>
        <SpecimenBill />
      </section>

      <section className="signin__form-side">
        <form className="signin__form" onSubmit={onSubmit} noValidate>
          <h2>Sign in</h2>
          <p className="signin__lead">Use your work email. You’ll be taken to your own workspace.</p>

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

          {error ? <p className="form-error" role="alert"><Icon name="alert" size={16} />{error}</p> : null}

          <button type="submit" className="button button--primary button--block" disabled={submitting}>
            {submitting ? 'Signing in…' : 'Sign in'}
          </button>
          <p className="signin__help">No account yet? Your administrator creates one for you.</p>
        </form>
      </section>
    </div>
  );
}
