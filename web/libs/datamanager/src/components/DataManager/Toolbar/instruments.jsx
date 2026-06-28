import { IconChevronDown } from "@humansignal/icons";
import { Block } from "../../../utils/bem";
import { FF_SELF_SERVE, isFF } from "../../../utils/feature-flags";
import { ErrorBox } from "../../Common/ErrorBox";
import { FieldsButton } from "../../Common/FieldsButton";
import { FiltersPane } from "../../Common/FiltersPane";
import { Icon } from "../../Common/Icon/Icon";
import { Interface } from "../../Common/Interface";
import { ExportButton, ImportButton } from "../../Common/SDKButtons";
import { Button, Spinner } from "@humansignal/ui";
import { inject, observer } from "mobx-react";
import { useEffect, useState } from "react";
import { Tooltip } from "@humansignal/ui";
import { Modal } from "../../Common/Modal/Modal";
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
  const isSelfServe =
    isFF(FF_SELF_SERVE) && window.APP_SETTINGS.billing?.enterprise === false;

  if (isOpenSource || !isSelfServe) return simpleButton;

  // Check if user is on trial
  const isTrialExpired = window.APP_SETTINGS.billing.checks?.is_license_expired;
  // Check the subscription period end date
  const subscriptionPeriodEnd =
    window.APP_SETTINGS.subscription?.current_period_end;
  // Check if user is self-serve and has expired trial
  const isSelfServeExpiredTrial =
    isSelfServe && isTrialExpired && !subscriptionPeriodEnd;
  // Check if user is self-serve and has expired subscription
  const isSelfServeExpiredSubscription =
    isSelfServe &&
    subscriptionPeriodEnd &&
    new Date(subscriptionPeriodEnd) < new Date();
  // Check if user is self-serve and has expired trial or subscription
  const isSelfServeExpired =
    isSelfServeExpiredTrial || isSelfServeExpiredSubscription;

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
    const ownerEmail =
      currentUser?.activeOrganizationMeta?.email ??
      currentUser?.active_organization_meta?.email;
    const membershipRole =
      currentUser?.activeOrganizationMembership?.role ??
      currentUser?.active_organization_membership?.role;
    const isOrganizationOwner =
      Boolean(currentUser?.isOwner) ||
      (Boolean(ownerEmail) && currentUser?.email === ownerEmail);
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
    const ExportMyAnnotationsButton = inject(({ store }) => ({
      projectId: store?.project?.id,
      store,
    }))(
      observer(({ projectId, store }) => {
        const [loading, setLoading] = useState(false);
        const [finalDisabled, setFinalDisabled] = useState(true);
        const [submissionStage, setSubmissionStage] = useState("idle");
        const [downloadUrl, setDownloadUrl] = useState("");
        const [downloadFilename, setDownloadFilename] = useState("");
        const [submissionErrorMessage, setSubmissionErrorMessage] =
          useState("");
        const [submissionStatusText, setSubmissionStatusText] = useState("");
        const [submissionProgressPercent, setSubmissionProgressPercent] =
          useState(0);
        const [submissionProgressDetail, setSubmissionProgressDetail] =
          useState("");
        const [lunorSubmissionId, setLunorSubmissionId] = useState(null);
        const currentUser = window.APP_SETTINGS?.user;
        const isOwner =
          Boolean(currentUser?.isOwner) ||
          (Boolean(currentUser?.activeOrganizationMeta?.email) &&
            currentUser?.email === currentUser?.activeOrganizationMeta?.email);

        if (isOwner) return null;

        const downloadExportedCsv = () => {
          if (!downloadUrl) return;

          const link = document.createElement("a");

          link.href = downloadUrl;
          link.download = downloadFilename || "final-submission.csv";
          document.body.appendChild(link);
          link.click();
          link.remove();
        };

        const resetSubmissionModal = () => {
          setDownloadUrl("");
          setDownloadFilename("");
          setSubmissionErrorMessage("");
          setSubmissionStatusText("");
          setSubmissionProgressPercent(0);
          setSubmissionProgressDetail("");
          setLunorSubmissionId(null);
          setSubmissionStage("idle");
        };

        // Check if final submission already exists to disable button
        useEffect(() => {
          const projectIdNum = Number(projectId ?? null);
          if (!projectIdNum) return;
          fetch(`/api/projects/${projectIdNum}/final-submission/check/`, {
            credentials: "include",
          })
            .then((resp) =>
              resp.ok
                ? resp.json()
                : Promise.reject(new Error(String(resp.status))),
            )
            .then((json) => {
              setFinalDisabled(Boolean(json?.exists));
              if (json?.lunor_submission_id) {
                setLunorSubmissionId(json.lunor_submission_id);
              }
            })
            .catch(() => {});
        }, [projectId]);

        useEffect(() => {
          if (submissionStage !== "loading") return;

          void onClick();
        }, [submissionStage]);

        const onClick = async () => {
          const app = window.APP_SETTINGS ?? {};
          const projectIdNum = Number(projectId ?? null);
          const djangoUserId = app?.user?.id ?? null;
          const lunorUserId = app?.user?.lunor_userId ?? "";

          if (!projectIdNum || !djangoUserId || !lunorUserId) {
            store?.SDK?.invoke?.("toast", {
              message: "Missing project or user information",
              type: "error",
            });
            setSubmissionErrorMessage("Missing project or user information.");
            setSubmissionStage("error");
            return;
          }

          try {
            setLoading(true);
            setSubmissionErrorMessage("");
            setLunorSubmissionId(null);
            setSubmissionStatusText("Verifying your final submission...");
            setSubmissionProgressPercent(0);
            setSubmissionProgressDetail("");

            const uploadResp = await fetch(
              `/api/lunor/submission-assets/upload/`,
              {
                method: "POST",
                credentials: "include",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({
                  studio_project_id: projectIdNum,
                  studio_user_id: djangoUserId,
                  lunor_userId: lunorUserId,
                }),
              },
            );

            const uploadJson = await uploadResp.json().catch(() => ({}));

            if (uploadResp.status === 409) {
              setFinalDisabled(true);
              throw new Error(
                uploadJson?.detail || "Final submission already exists.",
              );
            }

            if (!uploadResp.ok) {
              throw new Error(
                uploadJson?.detail ||
                  `Final submission request ${uploadResp.status}`,
              );
            }

            const submissionId =
              uploadJson?.lunor_submission_id ??
              uploadJson?.submission_id ??
              null;

            if (!submissionId) {
              throw new Error(
                "Final submission was accepted but no Lunor submission id was returned.",
              );
            }

            setLunorSubmissionId(submissionId);
            setFinalDisabled(true);
            setSubmissionStage("success");
            store?.SDK?.invoke?.("toast", {
              message: "Final submission accepted. Processing continues in the background.",
              type: "success",
            });
          } catch (err) {
            // eslint-disable-next-line no-console
            console.error("Failed to submit final annotations:", err);
            store?.SDK?.invoke?.("toast", {
              message: `Something went wrong. Please try again.`,
              type: "error",
            });
            setSubmissionErrorMessage(
              err instanceof Error
                ? err.message
                : "Something went wrong while processing your final submission.",
            );
            setSubmissionStage("error");
          } finally {
            setLoading(false);
          }
        };

        const modalTitle =
          submissionStage === "loading"
            ? "Verifying Final Submission"
            : submissionStage === "success"
              ? "Final Submission Accepted"
              : submissionStage === "error"
                ? "Final Submission Failed"
                : "Confirm Final Submission";

        const modalBody =
          submissionStage === "loading" ? (
            <div style={{ display: "grid", gap: 8 }}>
              <div style={{ display: "flex", justifyContent: "center" }}>
                <Spinner />
              </div>
              <div>
                {submissionStatusText ||
                  "Verifying your project, annotations, and Quest submission details."}
              </div>
            </div>
          ) : submissionStage === "success" ? (
            <div style={{ display: "grid", gap: 8 }}>
              <div>
                Your final submission has been accepted. Export and upload will
                continue in the background.
              </div>
              {lunorSubmissionId ? (
                <div>
                  Lunor submission ID:{" "}
                  <strong>{String(lunorSubmissionId)}</strong>
                </div>
              ) : null}
              <div>
                You can close this dialog and continue working. If background
                processing fails, the Final Submit button will become available
                again so you can retry.
              </div>
            </div>
          ) : submissionStage === "error" ? (
            <div style={{ display: "grid", gap: 8 }}>
              <div>Final submission failed.</div>
              <div>
                {submissionErrorMessage ||
                  "Something went wrong while exporting or uploading your annotations. Please try again."}
              </div>
              {downloadUrl ? (
                <div style={{ color: "red" }}>
                  Your annotations export is ready, but there was a problem
                  completing the final submission on the Quest platform. Please
                  download the CSV and contact support to complete the
                  submission.
                </div>
              ) : null}
            </div>
          ) : (
            <div style={{ display: "grid", gap: 8 }}>
              <div>
                This will verify your annotations and register your final
                submission with Quest.
              </div>
              <div>
                After confirming, you will receive your Lunor submission ID
                immediately. Export and upload will continue in the background.
              </div>
            </div>
          );

        const modalFooter =
          submissionStage === "loading" ? null : submissionStage ===
            "success" ? (
            <div
              style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}
            >
              <Button variant="primary" onClick={resetSubmissionModal}>
                Close
              </Button>
            </div>
          ) : submissionStage === "error" ? (
            <div
              style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}
            >
              <Button look="outlined" onClick={resetSubmissionModal}>
                Close
              </Button>
              {downloadUrl ? (
                <Button look="outlined" onClick={downloadExportedCsv}>
                  Download CSV
                </Button>
              ) : null}
              <Button
                variant="primary"
                onClick={() => {
                  setSubmissionErrorMessage("");
                  setSubmissionStage("loading");
                }}
              >
                Try Again
              </Button>
            </div>
          ) : (
            <div
              style={{ display: "flex", justifyContent: "flex-end", gap: 8 }}
            >
              <Button look="outlined" onClick={resetSubmissionModal}>
                Cancel
              </Button>
              <Button
                variant="primary"
                onClick={() => setSubmissionStage("loading")}
              >
                Confirm
              </Button>
            </div>
          );
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
          ? "Verifying your submission..."
          : finalDisabled
            ? "Final submission already submitted"
            : "Submit your annotations for evaluation";

        return (
          <>
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
                  onClick={() => {
                    if (loading || finalDisabled) return;
                    setSubmissionErrorMessage("");
                    setSubmissionStage("confirm");
                  }}
                  waiting={loading}
                  disabled={isDisabled}
                  aria-label="End Annotation"
                  style={styleOverride}
                >
                  Final Submit
                </Button>
              </Block>
            </Tooltip>
            {submissionStage !== "idle" ? (
              <Modal
                key={submissionStage}
                visible
                title={modalTitle}
                body={modalBody}
                footer={modalFooter}
                allowClose={submissionStage !== "loading"}
                closeOnClickOutside={submissionStage !== "loading"}
                onHide={() => {
                  if (submissionStage !== "loading") {
                    resetSubmissionModal();
                  }
                }}
              />
            ) : null}
          </>
        );
      }),
    );
    return (
      <Interface name="export">
        <ExportMyAnnotationsButton />
      </Interface>
    );
  },
};
