"use client";
import { useState, useEffect } from "react";
import { getTransactions, postTweet, TrackResponse, getAutoTweetStatus, toggleAutoTweet, updateAutoTweetSettings, AutoTweetStatus } from "../lib/api";
import styles from "./TransactionTracker.module.css";

export default function TransactionTracker() {
    const [data, setData] = useState<TrackResponse | null>(null);
    const [loading, setLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    const [tweetStatus, setTweetStatus] = useState<string | null>(null);
    const [autoTweetStatus, setAutoTweetStatus] = useState<AutoTweetStatus | null>(null);
    const [autoTweetLoading, setAutoTweetLoading] = useState(false);

    useEffect(() => {
        async function fetchData() {
            try {
                setLoading(true);
                setError(null);
                
                // Always fetch auto-tweet status first (this should work even when rate limited)
                const autoTweetResult = await getAutoTweetStatus();
                setAutoTweetStatus(autoTweetResult);
                
                // Try to fetch transaction data
                try {
                    const transactionResult = await getTransactions();
                    setData(transactionResult);
                } catch (transactionErr: any) {
                    // If rate limited, show a friendly message but still show the auto-tweet controls
                    if (transactionErr.message.includes('RATE_LIMIT_AUTO_TWEET:')) {
                        const message = transactionErr.message.replace('RATE_LIMIT_AUTO_TWEET: ', '');
                        setError(`⚠️ ${message}`);
                    } else if (transactionErr.message.includes('rate limit') || transactionErr.message.includes('429')) {
                        setError("⚠️ API rate limited - The system is currently fetching fresh data. The backend caches data for 5 minutes to avoid hitting rate limits. Auto-tweet monitoring is still active!");
                    } else {
                        throw transactionErr; // Re-throw other errors
                    }
                }
            } catch (err: any) {
                setError(err.message);
            } finally {
                setLoading(false);
            }
        }
        fetchData();
        
        // Set up periodic refresh every 30 seconds to retry when rate limit clears
        const interval = setInterval(async () => {
            if (error && (error.includes('rate limit') || error.includes('Auto-tweet monitoring'))) {
                try {
                    const transactionResult = await getTransactions();
                    setData(transactionResult);
                    setError(null); // Clear error when successful
                    console.log('✅ Successfully refreshed transaction data');
                } catch (err: any) {
                    // Silently fail on rate limit during background refresh
                    if (!err.message.includes('rate limit') && !err.message.includes('429') && !err.message.includes('RATE_LIMIT_AUTO_TWEET')) {
                        console.error('Background refresh failed:', err);
                    }
                }
            }
        }, 30000);
        
        return () => clearInterval(interval);
    }, [error]);

    async function handleTweet() {
        try {
            const res = await postTweet();
            setTweetStatus(res.tweet_preview);
        } catch (err: any) {
            setTweetStatus("❌ Error: " + err.message);
        }
    }

    async function handleToggleAutoTweet() {
        try {
            setAutoTweetLoading(true);
            const res = await toggleAutoTweet();
            setAutoTweetStatus(prev => prev ? { ...prev, enabled: res.enabled } : null);
            setTweetStatus(`✅ Auto-tweeting ${res.enabled ? 'enabled' : 'disabled'}`);
        } catch (err: any) {
            setTweetStatus("❌ Error: " + err.message);
        } finally {
            setAutoTweetLoading(false);
        }
    }

    async function handleUpdateSettings() {
        try {
            if (!autoTweetStatus) return;
            
            setAutoTweetLoading(true);
            const res = await updateAutoTweetSettings(
                autoTweetStatus.check_interval_seconds,
                autoTweetStatus.min_amount_tao
            );
            setTweetStatus("✅ Settings updated successfully");
        } catch (err: any) {
            setTweetStatus("❌ Error: " + err.message);
        } finally {
            setAutoTweetLoading(false);
        }
    }

    async function handleRefreshData() {
        try {
            setLoading(true);
            setError(null);
            const transactionResult = await getTransactions();
            setData(transactionResult);
            setTweetStatus("✅ Data refreshed successfully!");
        } catch (err: any) {
            if (err.message.includes('RATE_LIMIT_AUTO_TWEET:')) {
                const message = err.message.replace('RATE_LIMIT_AUTO_TWEET: ', '');
                setError(`⚠️ ${message}`);
            } else {
                setError(err.message);
            }
        } finally {
            setLoading(false);
        }
    }

    if (loading) return (
        <div className={styles.container}>
            <div className={styles.innerContainer}>
                <div className={styles.mainContent}>
                    <div className={styles.header}>
                        <h1 className={styles.headerTitle}>Bittensor Transaction Tracker</h1>
                        <p className={styles.headerSubtitle}>Loading transaction data...</p>
                    </div>
                    <p className={styles.loading}>⏳ Loading transactions...</p>
                </div>
            </div>
        </div>
    );

    // Show error but still render auto-tweet controls if available
    const showPartialUI = error && error.includes('rate limit') && autoTweetStatus;

    // If there's a non-rate-limit error and no data, show full error
    if (error && !showPartialUI && !data) {
        return (
            <div className={styles.container}>
                <div className={styles.innerContainer}>
                    <div className={styles.mainContent}>
                        <div className={styles.header}>
                            <h1 className={styles.headerTitle}>Bittensor Transaction Tracker</h1>
                            <p className={styles.headerSubtitle}>Connection Error</p>
                        </div>
                        <p className={styles.error}>❌ {error}</p>
                    </div>
                </div>
            </div>
        );
    }

    return (
        <div className={styles.container}>
            <div className={styles.innerContainer}>
                <div className={styles.mainContent}>
                    {/* Header */}
                    <div className={styles.header}>
                        <h1 className={styles.headerTitle}>Bittensor Transaction Tracker</h1>
                        <p className={styles.headerSubtitle}>
                            {showPartialUI 
                                ? "Auto-tweet monitoring active - Transaction data temporarily unavailable due to rate limiting"
                                : "Real-time blockchain transaction monitoring and analytics"
                            }
                        </p>
                    </div>

                    {/* Show rate limit notice if applicable */}
                    {showPartialUI && (
                        <div className={styles.section}>
                            <div className={styles.rateLimitNotice}>
                                <p className={styles.error}>⚠️ {error}</p>
                                <p className={styles.infoText}>The auto-tweet feature is still monitoring for new transactions in the background.</p>
                                <button
                                    onClick={handleRefreshData}
                                    disabled={loading}
                                    className={`${styles.button} ${styles.buttonSmall}`}
                                >
                                    {loading ? '⏳ Refreshing...' : '🔄 Try Refresh'}
                                </button>
                            </div>
                        </div>
                    )}

                    {/* Auto-Tweet Controls */}
                    <div className={styles.section}>
                        <h2 className={styles.sectionTitle}>🤖 Auto-Tweet Settings</h2>
                        {autoTweetStatus && (
                            <div className={styles.autoTweetControls}>
                                <div className={styles.statusIndicator}>
                                    <div className={styles.statusBadge}>
                                        <span className={`${styles.statusDot} ${autoTweetStatus.enabled ? styles.active : styles.inactive}`}></span>
                                        Status: {autoTweetStatus.enabled ? 'Active' : 'Inactive'}
                                    </div>
                                    {autoTweetStatus.last_check && (
                                        <div className={styles.lastCheck}>
                                            Last checked: {new Date(autoTweetStatus.last_check).toLocaleTimeString()}
                                        </div>
                                    )}
                                </div>

                                <div className={styles.settingsGrid}>
                                    <div className={styles.settingItem}>
                                        <label className={styles.settingLabel}>Check Interval (seconds)</label>
                                        <input
                                            type="number"
                                            value={autoTweetStatus.check_interval_seconds}
                                            onChange={(e) => setAutoTweetStatus({
                                                ...autoTweetStatus,
                                                check_interval_seconds: parseInt(e.target.value) || 60
                                            })}
                                            min="30"
                                            className={styles.settingInput}
                                        />
                                    </div>
                                    
                                    <div className={styles.settingItem}>
                                        <label className={styles.settingLabel}>Min Amount (TAO)</label>
                                        <input
                                            type="number"
                                            step="0.1"
                                            value={autoTweetStatus.min_amount_tao}
                                            onChange={(e) => setAutoTweetStatus({
                                                ...autoTweetStatus,
                                                min_amount_tao: parseFloat(e.target.value) || 0.1
                                            })}
                                            min="0"
                                            className={styles.settingInput}
                                        />
                                    </div>
                                </div>

                                <div className={styles.controlButtons}>
                                    <button
                                        onClick={handleToggleAutoTweet}
                                        disabled={autoTweetLoading}
                                        className={`${styles.button} ${autoTweetStatus.enabled ? styles.buttonDanger : styles.buttonSuccess}`}
                                    >
                                        {autoTweetLoading ? '⏳ Loading...' : (autoTweetStatus.enabled ? '⏹ Disable Auto-Tweet' : '▶️ Enable Auto-Tweet')}
                                    </button>
                                    
                                    <button
                                        onClick={handleUpdateSettings}
                                        disabled={autoTweetLoading}
                                        className={styles.button}
                                    >
                                        {autoTweetLoading ? '⏳ Updating...' : '💾 Save Settings'}
                                    </button>
                                </div>

                                <div className={styles.monitoringInfo}>
                                    <p className={styles.infoText}>
                                        📈 Monitoring: {autoTweetStatus.known_transactions.transfers_in} incoming, {autoTweetStatus.known_transactions.transfers_out} outgoing transactions
                                    </p>
                                    <p className={styles.infoText}>
                                        🐦 New transactions will be automatically posted to Twitter when detected
                                    </p>
                                    {error && error.includes('Auto-tweet monitoring') && (
                                        <p className={styles.infoText}>
                                            ✅ Auto-tweet monitoring is active and running independently of the frontend display
                                        </p>
                                    )}
                                </div>
                            </div>
                        )}
                    </div>

                    {/* Summary - only show if we have data */}
                    {data && (
                        <>
                            <div className={styles.section}>
                                <h2 className={styles.sectionTitle}>📊 Transaction Summary</h2>
                                {data?.summary && (
                                    <div className={styles.summaryGrid}>
                                        <div className={styles.summaryCard}>
                                            <div className={styles.summaryLabel}>Total Inbound</div>
                                            <div className={styles.summaryValue}>{data.solana_to_bittensor.length}</div>
                                        </div>
                                        <div className={styles.summaryCard}>
                                            <div className={styles.summaryLabel}>Total Outbound</div>
                                            <div className={styles.summaryValue}>{data.bittensor_to_solana.length}</div>
                                        </div>
                                        <div className={styles.summaryCard}>
                                            <div className={styles.summaryLabel}>Total Volume</div>
                                            <div className={styles.summaryValue}>
                                                {(data.solana_to_bittensor.reduce((sum, tx) => sum + parseFloat(String(tx.amount || 0)), 0) +
                                                  data.bittensor_to_solana.reduce((sum, tx) => sum + parseFloat(String(tx.amount || 0)), 0)).toFixed(2)} TAO
                                            </div>
                                        </div>
                                    </div>
                                )}
                                <pre className={styles.summaryBox}>
                                    {JSON.stringify(data?.summary, null, 2)}
                                </pre>
                            </div>

                            {/* Transfers In */}
                            <div className={styles.section}>
                                <h2 className={styles.sectionTitle}>➡ In (Bittensor → Solana)</h2>
                                {data?.solana_to_bittensor.length === 0 ? (
                                    <p className={styles.noData}>No inbound transfers</p>
                                ) : (
                                    <div className={styles.transactionTable}>
                                        <div className={styles.tableHeader}>
                                            <div>#</div>
                                            <div>From Address</div>
                                            <div>To Address</div>
                                            <div>Amount</div>
                                            <div>Timestamp</div>
                                        </div>
                                        <ul className={styles.transactionList}>
                                            {data?.solana_to_bittensor.map((tx, i) => (
                                                <li key={i} className={styles.transactionItem}>
                                                    <div className={styles.txNumber}>{i + 1}</div>
                                                    <div className={styles.fromAddress}>{tx.from_ss58 ? `${tx.from_ss58.substring(0, 8)}...${tx.from_ss58.substring(tx.from_ss58.length - 6)}` : 'N/A'}</div>
                                                    <div className={styles.toAddress}>{tx.to_ss58 ? `${tx.to_ss58.substring(0, 8)}...${tx.to_ss58.substring(tx.to_ss58.length - 6)}` : 'N/A'}</div>
                                                    <div className={styles.txAmount}>{tx.amount} TAO</div>
                                                    <div className={styles.txTimestamp}>{tx.timestamp}</div>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </div>

                            {/* Transfers Out */}
                            <div className={styles.section}>
                                <h2 className={styles.sectionTitle}>⬅ Out (Solana → Bittensor)</h2>
                                {data?.bittensor_to_solana.length === 0 ? (
                                    <p className={styles.noData}>No outbound transfers</p>
                                ) : (
                                    <div className={styles.transactionTable}>
                                        <div className={styles.tableHeader}>
                                            <div>#</div>
                                            <div>From Address</div>
                                            <div>To Address</div>
                                            <div>Amount</div>
                                            <div>Timestamp</div>
                                        </div>
                                        <ul className={styles.transactionList}>
                                            {data?.bittensor_to_solana.map((tx, i) => (
                                                <li key={i} className={styles.transactionItem}>
                                                    <div className={styles.txNumber}>{i + 1}</div>
                                                    <div className={styles.fromAddress}>{tx.from_ss58 ? `${tx.from_ss58.substring(0, 8)}...${tx.from_ss58.substring(tx.from_ss58.length - 6)}` : 'N/A'}</div>
                                                    <div className={styles.toAddress}>{tx.to_ss58 ? `${tx.to_ss58.substring(0, 8)}...${tx.to_ss58.substring(tx.to_ss58.length - 6)}` : 'N/A'}</div>
                                                    <div className={styles.txAmount}>{tx.amount} TAO</div>
                                                    <div className={styles.txTimestamp}>{tx.timestamp}</div>
                                                </li>
                                            ))}
                                        </ul>
                                    </div>
                                )}
                            </div>
                        </>
                    )}

                    {/* Tweet Button */}
                    <button
                        onClick={handleTweet}
                        className={styles.button}
                    >
                        🐦 Tweet Summary
                    </button>

                    {tweetStatus && (
                        <p className={styles.success}>{tweetStatus}</p>
                    )}
                </div>
            </div>
        </div>
    );
}
