import { createContext, memo, useContext, useMemo } from "react";
import type { APIUser } from "../types/user";
import { useCurrentUserAtom } from "../lib/hooks/useCurrentUser";

export enum ABILITY {
  can_create_tokens = "users.token.any",
}

export type Ability = ABILITY;

export type AuthPermissions = {
  can: (a: string) => boolean;
  canAny: (as: string[]) => boolean;
  canAll: (as: string[]) => boolean;
};

type AuthState = {
  user?: APIUser;
  refetch: () => Promise<void> | void;
  permissions: AuthPermissions;
};

const AuthContext = createContext<AuthState | null>(null);

const makePermissionChecker = (list?: (Ability | string)[]) => {
  const abilities = new Set<string>((list as string[]) ?? []);
  const has = (a: string) => {
    if (abilities.size === 0) return false;
    if (abilities.has(`-${a}`)) return false;
    if (abilities.has("*")) return true;
    return abilities.has(a);
  };
  return {
    can: (a: string) => has(a),
    canAny: (arr: string[]) => arr.some((a) => !abilities.has(`-${a}`) && (abilities.has("*") || abilities.has(a))),
    canAll: (arr: string[]) => arr.every((a) => !abilities.has(`-${a}`) && (abilities.has("*") || abilities.has(a))),
  };
};

export const AuthProvider = memo<{ children: React.ReactNode }>(({ children }) => {
  const { user, fetch } = useCurrentUserAtom();

  const checker = useMemo(() => makePermissionChecker(user?.permissions), [user?.permissions]);
  const permissionHelpers = useMemo<AuthPermissions>(() => {
    return {
      can: (a: string) => checker.can(String(a)),
      canAny: (abilities: string[]) => checker.canAny(abilities.map((a) => String(a))),
      canAll: (abilities: string[]) => checker.canAll(abilities.map((a) => String(a))),
    };
  }, [checker]);

  const contextValue: AuthState = useMemo(() => {
    return {
      user: user ?? undefined,
      refetch: fetch,
      permissions: permissionHelpers,
    };
  }, [user, fetch, permissionHelpers]);

  return <AuthContext.Provider value={contextValue}>{children}</AuthContext.Provider>;
});

export const useAuth = () => {
  const ctx = useContext(AuthContext)!;

  return {
    user: ctx?.user,
    permissions: ctx.permissions,
    refetch: ctx?.refetch,
  };
};
