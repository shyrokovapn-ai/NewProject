const REGION = import.meta.env.VITE_COGNITO_REGION || "us-east-1";
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID;
const KEY = "spry_id_token";

function expired(token) {
  try {
    const { exp } = JSON.parse(atob(token.split(".")[1].replace(/-/g, "+").replace(/_/g, "/")));
    return exp * 1000 < Date.now() + 30_000;
  } catch {
    return true;
  }
}

export function getToken() {
  const token = sessionStorage.getItem(KEY);
  return token && !expired(token) ? token : null;
}

export const signOut = () => sessionStorage.removeItem(KEY);

export async function signIn(email, password) {
  const res = await fetch(`https://cognito-idp.${REGION}.amazonaws.com/`, {
    method: "POST",
    headers: {
      "content-type": "application/x-amz-json-1.1",
      "x-amz-target": "AWSCognitoIdentityProviderService.InitiateAuth",
    },
    body: JSON.stringify({
      AuthFlow: "USER_PASSWORD_AUTH",
      ClientId: CLIENT_ID,
      AuthParameters: { USERNAME: email, PASSWORD: password },
    }),
  });
  const data = await res.json();
  const token = data.AuthenticationResult?.IdToken;
  if (!token) throw new Error("Wrong email or password");
  sessionStorage.setItem(KEY, token);
  return token;
}
