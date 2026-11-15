// Amazon Cognito sign-in for family members.
import {
  AuthenticationDetails, CognitoUser, CognitoUserAttribute, CognitoUserPool, type CognitoUserSession,
} from "amazon-cognito-identity-js";

const pool = new CognitoUserPool({
  UserPoolId: (import.meta.env.VITE_COGNITO_POOL_ID as string) || "us-east-2_E6Rbcn9Io",
  ClientId: (import.meta.env.VITE_COGNITO_CLIENT_ID as string) || "qm4gr0n0so4883ujugg3iqf1r",
});

const userFor = (email: string) => new CognitoUser({ Username: email.trim().toLowerCase(), Pool: pool });

export function idToken(): Promise<string | null> {
  const u = pool.getCurrentUser();
  if (!u) return Promise.resolve(null);
  return new Promise((resolve) => {
    u.getSession((err: Error | null, s: CognitoUserSession | null) => {
      resolve(err || !s || !s.isValid() ? null : s.getIdToken().getJwtToken());
    });
  });
}

export function signIn(email: string, password: string): Promise<void> {
  return new Promise((resolve, reject) => {
    userFor(email).authenticateUser(
      new AuthenticationDetails({ Username: email.trim().toLowerCase(), Password: password }),
      { onSuccess: () => resolve(), onFailure: (e) => reject(friendly(e)) },
    );
  });
}

export function signUp(name: string, email: string, password: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const attrs = [new CognitoUserAttribute({ Name: "name", Value: name.trim() })];
    pool.signUp(email.trim().toLowerCase(), password, attrs, [], (e) => (e ? reject(friendly(e)) : resolve()));
  });
}

export function confirmSignUp(email: string, code: string): Promise<void> {
  return new Promise((resolve, reject) => {
    userFor(email).confirmRegistration(code.trim(), true, (e) => (e ? reject(friendly(e)) : resolve()));
  });
}

export function resendCode(email: string): Promise<void> {
  return new Promise((resolve, reject) => {
    userFor(email).resendConfirmationCode((e) => (e ? reject(friendly(e)) : resolve()));
  });
}

export function signOut() {
  pool.getCurrentUser()?.signOut();
}

function friendly(e: unknown): Error {
  const err = e as { code?: string; message?: string };
  const map: Record<string, string> = {
    NotAuthorizedException: "That email and password don't match.",
    UserNotFoundException: "That email and password don't match.",
    UserNotConfirmedException: "UNCONFIRMED",
    UsernameExistsException: "There's already an account with that email. Try signing in.",
    InvalidPasswordException: "Use at least 8 characters, including a number.",
    CodeMismatchException: "That code isn't right. Check the email and try again.",
    ExpiredCodeException: "That code expired. Send a new one.",
    LimitExceededException: "Too many tries. Wait a minute and try again.",
  };
  return new Error((err.code && map[err.code]) || err.message || "Something went wrong.");
}
