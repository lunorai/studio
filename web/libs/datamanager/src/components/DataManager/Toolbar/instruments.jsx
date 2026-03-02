import { IconChevronDown } from "@humansignal/icons";
import { Block } from "../../../utils/bem";
import { FF_SELF_SERVE, isFF } from "../../../utils/feature-flags";
import { ErrorBox } from "../../Common/ErrorBox";
import { FieldsButton } from "../../Common/FieldsButton";
import { FiltersPane } from "../../Common/FiltersPane";
import { Icon } from "../../Common/Icon/Icon";
import { Interface } from "../../Common/Interface";
import { ExportButton, ImportButton } from "../../Common/SDKButtons";
import { Button } from "@humansignal/ui";
import { inject, observer } from "mobx-react";
import { useState } from "react";
import { Tooltip } from "@humansignal/ui";
import { ActionsButton } from "./ActionsButton";
import { GridWidthButton } from "./GridWidthButton";
import { LabelButton } from "./LabelButton";
import { LoadingPossum } from "./LoadingPossum";
import { OrderButton } from "./OrderButton";
import { RefreshButton } from "./RefreshButton";
import { ViewToggle } from "./ViewToggle";

const style = {
  minWidth: "80px",
  justifyContent: "space-between",
};

/**
 * Checks for Starter Cloud trial expiration.
 * If expired it renders disabled Import button with a tooltip.
 */
const ImportButtonWithChecks = ({ size }) => {
  const simpleButton = <ImportButton size={size}>Import</ImportButton>;
  const isOpenSource = !window.APP_SETTINGS.billing;
  // Check if user is self-serve; Enterprise flag === false is the main condition
  const isSelfServe = isFF(FF_SELF_SERVE) && window.APP_SETTINGS.billing?.enterprise === false;

  if (isOpenSource || !isSelfServe) return simpleButton;

  // Check if user is on trial
  const isTrialExpired = window.APP_SETTINGS.billing.checks?.is_license_expired;
  // Check the subscription period end date
  const subscriptionPeriodEnd = window.APP_SETTINGS.subscription?.current_period_end;
  // Check if user is self-serve and has expired trial
  const isSelfServeExpiredTrial = isSelfServe && isTrialExpired && !subscriptionPeriodEnd;
  // Check if user is self-serve and has expired subscription
  const isSelfServeExpiredSubscription =
    isSelfServe && subscriptionPeriodEnd && new Date(subscriptionPeriodEnd) < new Date();
  // Check if user is self-serve and has expired trial or subscription
  const isSelfServeExpired = isSelfServeExpiredTrial || isSelfServeExpiredSubscription;

  if (!isSelfServeExpired) return simpleButton;

  // Disabled buttons ignore hover, so we use wrapper to properly handle a tooltip
  return (
    <Tooltip
      title="You must upgrade your plan to import data"
      style={{
        maxWidth: 200,
        textAlign: "center",
      }}
    >
      <Block name="button-wrapper">
        <ImportButton disabled size={size}>
          Import
        </ImportButton>
      </Block>
    </Tooltip>
  );
};

export const instruments = {
  "view-toggle": ({ size }) => {
    return <ViewToggle size={size} style={style} />;
  },
  columns: ({ size }) => {
    const iconProps = {
      style: {
        marginRight: 4,
      },
      icon: IconChevronDown,
    };
    return (
      <FieldsButton
        wrapper={FieldsButton.Checkbox}
        trailingIcon={<Icon {...iconProps} />}
        title={"Columns"}
        size={size}
        style={style}
        openUpwardForShortViewport={false}
      />
    );
  },
  filters: ({ size }) => {
    return <FiltersPane size={size} style={style} />;
  },
  ordering: ({ size }) => {
    return <OrderButton size={size} style={style} />;
  },
  "grid-size": ({ size }) => {
    return <GridWidthButton size={size} />;
  },
  refresh: ({ size }) => {
    return <RefreshButton size={size} />;
  },
  "loading-possum": () => {
    return <LoadingPossum />;
  },
  "label-button": ({ size }) => {
    return <LabelButton size={size} />;
  },
  actions: ({ size }) => {
    const currentUser = window.APP_SETTINGS?.user;
    const ownerEmail = currentUser?.activeOrganizationMeta?.email ?? currentUser?.active_organization_meta?.email;
    const membershipRole =
      currentUser?.activeOrganizationMembership?.role ?? currentUser?.active_organization_membership?.role;
    const isOrganizationOwner = Boolean(currentUser?.isOwner) || (Boolean(ownerEmail) && currentUser?.email === ownerEmail);
    const isOrganizationAdmin = membershipRole === "AD";

    if (!isOrganizationOwner && !isOrganizationAdmin) return null;

    return <ActionsButton size={size} style={style} />;
  },
  "error-box": () => {
    return <ErrorBox />;
  },
  "import-button": ({ size }) => {
    return (
      <Interface name="import">
        <ImportButtonWithChecks size={size} />
      </Interface>
    );
  },
  "export-button": ({ size }) => {
    return (
      <Interface name="export">
        <ExportButton size={size}>Export</ExportButton>
      </Interface>
    );
  },
  "export-my-annotations": ({ size }) => {
    const ExportMyAnnotationsButton = inject(({ store }) => ({ projectId: store?.project?.id, store }))(
      observer(({ projectId, store }) => {
        const [loading, setLoading] = useState(false);
        const [finalDisabled, setFinalDisabled] = useState(true);
        const currentUser = window.APP_SETTINGS?.user;
        const isOwner = Boolean(currentUser?.isOwner) || (
          Boolean(currentUser?.activeOrganizationMeta?.email) && currentUser?.email === currentUser?.activeOrganizationMeta?.email
        );

        if (isOwner) return null;

        // Check if final submission already exists to disable button
        useState(() => {
          const projectIdNum = Number(projectId ?? null);
          if (!projectIdNum) return;
          fetch(`/api/projects/${projectIdNum}/final-submission/check/`, { credentials: "include" })
            .then((resp) => resp.ok ? resp.json() : Promise.reject(new Error(String(resp.status))))
            .then((json) => setFinalDisabled(Boolean(json?.exists)))
            .catch(() => {});
        });

        const onClick = async () => {
          const app = window.APP_SETTINGS ?? {};
          const projectIdNum = Number(projectId ?? null);
          const djangoUserId = app?.user?.id ?? null;

          if (!projectIdNum || !djangoUserId) {
            store?.SDK?.invoke?.("toast", { message: "Missing project or user information", type: "error" });
            return;
          }

          try {
            setLoading(true);

            // 1) Create an async export snapshot containing only current user's annotations
            const createResp = await fetch(`/api/projects/${projectIdNum}/exports/`, {
              method: "POST",
              credentials: "include",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                title: "Final submission (my annotations)",
                task_filter_options: {
                  annotated: "only",
                  only_with_annotations: true,
                  completed_by: djangoUserId,
                },
                annotation_filter_options: {
                  usual: true,
                  completed_by: djangoUserId,
                },
                serialization_options: {
                  include_annotation_history: false,
                  interpolate_key_frames: false,
                },
              }),
            });

            if (!createResp.ok) throw new Error(`Export create ${createResp.status}`);

            const createJson = await createResp.json();
            const exportId = createJson?.id;

            if (!exportId) throw new Error("No export id returned");

            // 2) Poll export snapshot status until completed
            const delay = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
            const maxAttempts = 60;

            for (let attempt = 0; attempt < maxAttempts; attempt += 1) {
              const statusResp = await fetch(`/api/projects/${projectIdNum}/exports/${exportId}`, {
                credentials: "include",
              });

              if (!statusResp.ok) throw new Error(`Export status ${statusResp.status}`);

              const statusJson = await statusResp.json();
              const status = statusJson?.status;

              if (status === "completed") break;
              if (status === "failed") throw new Error("Export failed");

              await delay(3000);

              if (attempt === maxAttempts - 1) {
                throw new Error("Export timed out");
              }
            }

            // 3) Download CSV for completed export snapshot
            const params = new URLSearchParams({ exportType: "CSV" });
            const downloadResp = await fetch(
              `/api/projects/${projectIdNum}/exports/${exportId}/download?${params.toString()}`,
              {
                credentials: "include",
              },
            );

            if (!downloadResp.ok) throw new Error(`Export download ${downloadResp.status}`);

            const blob = await downloadResp.blob();

            // Prepare upload params
            const fallback = `annotations-${app?.user?.id || "me"}.csv`;
            const filenameHeader = downloadResp.headers.get("filename");
            const filename = (filenameHeader || fallback).replace(/\.json$/i, ".csv");
            const challengeId = Number(store?.project?.challenge_id ?? null);
            const round = store?.project?.round ?? 1;
            const userId = app?.user?.lunor_userId ?? "";

            const runtimeGraphql = window.APP_SETTINGS?.graphql_endpoint && String(window.APP_SETTINGS.graphql_endpoint);
            const graphqlEndpoint = runtimeGraphql || process.env.GRAPHQL_ENDPOINT || "https://feat.100protocol.com/";
            // GraphQL query to request an upload URL to R2
            const gqlQuery = `query($challengeId: Int!, $userId: String!, $round: Int!, $filename: String!) {\n  getAnnotationUploadUrl(challengeId: $challengeId, userId: $userId, round: $round, filename: $filename) {\n    challengeId\n    round\n    submissionId\n    maxConcurrentUploadLimit\n    urlArr { url key }\n  }\n}`;

            const gqlResp = await fetch(graphqlEndpoint, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
              },
              body: JSON.stringify({
                query: gqlQuery,
                variables: { challengeId, userId, round, filename },
              }),
              // credentials: "include",
            });
            if (!gqlResp.ok) throw new Error(`GraphQL ${gqlResp.status}`);
            const gqlJson = await gqlResp.json();
            const uploadInfo = gqlJson?.data?.getAnnotationUploadUrl;
            const uploadUrl = uploadInfo?.urlArr?.[0]?.url;
            if (!uploadUrl) throw new Error("No upload URL returned");

            // Upload CSV blob to R2 using the signed URL
            const putResp = await fetch(uploadUrl, {
              method: "PUT",
              body: blob,
              headers: {
                "Content-Type": "text/csv",
              },
            });
            if (!putResp.ok) throw new Error(`Upload ${putResp.status}`);

            // After successful upload, notify backend with UpdateSubmissionAssetList
            // Use the key(s) returned by getAnnotationUploadUrl, do not use filename
            const assetKeys = Array.isArray(uploadInfo?.urlArr)
              ? uploadInfo.urlArr.map((item) => item?.key).filter(Boolean)
              : [];
            if (assetKeys.length === 0) throw new Error("No asset keys returned from getAnnotationUploadUrl");
            const updateMutation = `mutation UpdateSubmissionAssetList($submissionId: Int, $challengeId: Int, $round: Int, $userId: String!, $asset_list: [String!]!) {\n  updateSubmissionAssetList(\n    submissionId: $submissionId\n    challengeId: $challengeId\n    round: $round\n    userId: $userId\n    asset_list: $asset_list\n  )\n}`;

            const updateResp = await fetch(graphqlEndpoint, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              // credentials: "include",
              body: JSON.stringify({
                query: updateMutation,
                variables: {
                  submissionId: uploadInfo?.submissionId ?? null,
                  challengeId,
                  round,
                  userId,
                  asset_list: assetKeys,
                },
              }),
            });
            if (!updateResp.ok) throw new Error(`UpdateSubmissionAssetList ${updateResp.status}`);

            // Notify success
            store?.SDK?.invoke?.("toast", { message: "Submission uploaded successfully", type: "success" });

            // Record final submission in backend and disable button
            try {
              if (projectIdNum) {
                const recResp = await fetch(`/api/projects/${projectIdNum}/final-submission/`, {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  credentials: "include",
                  body: JSON.stringify({}),
                });
                if (recResp.ok) setFinalDisabled(true);
              }
            } catch (_) {}
          } catch (err) {
            // eslint-disable-next-line no-console
            console.error("Failed to export annotations by me:", err);
            store?.SDK?.invoke?.("toast", { message: `Something went wrong. Please try again.`, type: "error" });
          } finally {
            setLoading(false);
          }
        };
        const styleOverride = loading
          ? {
              "--wait-color-value": "#EABE00",
              "--wait-color-value-outline": "#EABE00",
              "--text-color": "#ccc",
            }
          : {
              "--wait-color-value": "#EABE00",
              "--wait-color-value-outline": "#EABE00",
            };

        const isDisabled = loading || finalDisabled;
        const tooltipTitle = loading
          ? "Uploading your submission..."
          : finalDisabled
          ? "Final submission already exists"
          : "Submit your annotations for evaluation";

        return (
          <Tooltip
            title={tooltipTitle}
            style={{
              maxWidth: 260,
              textAlign: "center",
            }}
          >
            <Block name="button-wrapper">
              <Button
                size={size}
                look="outlined"
                variant="primary"
                onClick={onClick}
                waiting={loading}
                disabled={isDisabled}
                aria-label="End Annotation"
                style={styleOverride}
              >
                Final Submit
              </Button>
            </Block>
          </Tooltip>
        );
      }),
    );
    return <Interface name="export"><ExportMyAnnotationsButton /></Interface>;
  },
};
