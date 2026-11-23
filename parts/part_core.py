"""Core models, PrefsRepo, UrlNormalizer, ErrorSanitizer, Theme, and AppContainer."""

FILES = {
    "app/src/main/java/com/clippulse/app/domain/model/Models.kt": r'''
package com.clippulse.app.domain.model

sealed class AppResult<out T> {
    data class Success<T>(val data: T) : AppResult<T>()
    data class Error(
        val message: String,
        val code: Int? = null,
        val cause: Throwable? = null
    ) : AppResult<Nothing>()

    fun getOrNull(): T? = (this as? Success)?.data

    inline fun <R> map(transform: (T) -> R): AppResult<R> = when (this) {
        is Success -> Success(transform(data))
        is Error -> this
    }
}

enum class SignalType(val label: String, val colorHex: Long) {
    HEATMAP("Heatmap", 0xFFEF4444),
    SUPER_CHAT("Super Chat", 0xFFF59E0B),
    CHAT_VELOCITY("Chat Hype", 0xFFA855F7),
    AI_PICK("AI Pick", 0xFF06B6D4),
    AUDIO_EXCITEMENT("Transcript", 0xFF10B981)
}

data class Signal(
    val start: Double,
    val end: Double,
    val score: Double,
    val type: SignalType,
    val label: String = "",
    val meta: String = ""
)

data class HeatmapPoint(
    val startSec: Double,
    val endSec: Double,
    val value: Double
)

data class SuperChatEvent(
    val timestampSec: Double,
    val author: String,
    val amountText: String,
    val message: String,
    val tierColorHex: Long = 0xFFF59E0B
)

data class VideoMetadata(
    val id: String,
    val sourceUrl: String,
    val title: String,
    val uploader: String,
    val durationSec: Double,
    val previewStreamUrl: String,
    val streamHeaders: Map<String, String> = emptyMap(),
    val isLocalFile: Boolean = false,
    val localUri: String? = null,
    val thumbnailUrl: String? = null,
    val heatmap: List<HeatmapPoint> = emptyList(),
    val superChats: List<SuperChatEvent> = emptyList(),
    val transcriptSnippet: String = ""
)

data class ViralCopyPack(
    val titles: List<String>,
    val hook: String,
    val description: String,
    val hashtags: List<String>
)

data class ClipCandidate(
    val id: String,
    val startSec: Double,
    val endSec: Double,
    val score: Double,
    val primarySignal: SignalType,
    val signals: List<SignalType>,
    val title: String,
    val reason: String,
    val superChat: SuperChatEvent? = null,
    val copyPack: ViralCopyPack? = null,
    val isCustom: Boolean = false
) {
    val durationSec: Double
        get() = (endSec - startSec).coerceAtLeast(0.0)
}

data class ExportConfig(
    val clip: ClipCandidate,
    val metadata: VideoMetadata,
    val aspect9x16: Boolean = true,
    val cropOffsetX: Float = 0.5f,
    val fastCutBypass: Boolean = false,
    val burnSuperChatOverlay: Boolean = true,
    val applyLoudnorm: Boolean = true,
    val writeSidecarTxt: Boolean = true
)

data class ExportProgress(
    val jobId: String,
    val clipTitle: String,
    val stage: String,
    val progress: Float,
    val isRunning: Boolean,
    val outputUri: String? = null,
    val error: String? = null
)

data class ExportRecord(
    val id: String,
    val clipTitle: String,
    val sourceTitle: String,
    val durationSec: Double,
    val fileName: String,
    val contentUri: String,
    val sidecarUri: String? = null,
    val fileSizeBytes: Long,
    val createdAtMs: Long,
    val aspect9x16: Boolean
)

data class ScanHistoryItem(
    val id: String,
    val sourceUrl: String,
    val title: String,
    val uploader: String,
    val durationSec: Double,
    val clipCount: Int,
    val scannedAtMs: Long,
    val isLocalFile: Boolean = false
)

enum class StoragePreset(val id: String, val label: String, val relativePath: String) {
    MOVIES_CLIPPULSE("movies", "Movies / ClipPulse", "Movies/ClipPulse"),
    DOWNLOADS_CLIPPULSE("downloads", "Downloads / ClipPulse", "Download/ClipPulse"),
    DCIM_CLIPPULSE("dcim", "DCIM / ClipPulse", "DCIM/ClipPulse"),
    CUSTOM_SAF("saf", "Custom Folder (SAF)", "");

    companion object {
        fun fromId(id: String?): StoragePreset =
            entries.firstOrNull { it.id == id } ?: MOVIES_CLIPPULSE
    }
}

enum class AiPreset(
    val id: String,
    val displayName: String,
    val defaultBaseUrl: String,
    val defaultModel: String
) {
    GEMINI_COMPAT(
        "gemini",
        "Gemini OpenAI-Compat",
        "https://generativelanguage.googleapis.com/v1beta/openai",
        "gemini-2.0-flash-lite"
    ),
    DEEPSEEK(
        "deepseek",
        "DeepSeek",
        "https://api.deepseek.com/v1",
        "deepseek-chat"
    ),
    OPENAI(
        "openai",
        "OpenAI",
        "https://api.openai.com/v1",
        "gpt-4o-mini"
    ),
    OPENROUTER(
        "openrouter",
        "OpenRouter",
        "https://openrouter.ai/api/v1",
        "google/gemini-2.0-flash-lite-001"
    ),
    GROQ(
        "groq",
        "Groq",
        "https://api.groq.com/openai/v1",
        "llama-3.1-8b-instant"
    ),
    CUSTOM(
        "custom",
        "Custom Gateway",
        "https://api.openai.com/v1",
        "gpt-4o-mini"
    );

    companion object {
        fun fromId(id: String?): AiPreset =
            entries.firstOrNull { it.id == id } ?: GEMINI_COMPAT
    }
}

data class AiConfig(
    val preset: AiPreset = AiPreset.GEMINI_COMPAT,
    val baseUrl: String = AiPreset.GEMINI_COMPAT.defaultBaseUrl,
    val apiKeys: List<String> = listOf("", "", "", ""),
    val activeKeyIndex: Int = 0,
    val model: String = AiPreset.GEMINI_COMPAT.defaultModel,
    val isConnected: Boolean = false,
    val lastConnectedModel: String = "",
    val offlineMode: Boolean = false
) {
    fun usableKeys(): List<Pair<Int, String>> =
        apiKeys.mapIndexedNotNull { idx, key ->
            val trimmed = key.trim()
            if (trimmed.isNotEmpty()) idx to trimmed else null
        }
}
''',

    "app/src/main/java/com/clippulse/app/util/UrlNormalizer.kt": r'''
package com.clippulse.app.util

import android.net.Uri
import java.util.Locale

object UrlNormalizer {

    fun normalizeAiBaseUrl(raw: String): String {
        var url = raw.trim()
        if (url.isEmpty()) return "https://api.openai.com/v1"
        if (!url.startsWith("http://", ignoreCase = true) &&
            !url.startsWith("https://", ignoreCase = true)
        ) {
            url = "https://$url"
        }
        url = url.trimEnd('/')
        val suffixes = listOf(
            "/chat/completions",
            "/completions",
            "/models"
        )
        for (suffix in suffixes) {
            if (url.endsWith(suffix, ignoreCase = true)) {
                url = url.dropLast(suffix.length).trimEnd('/')
            }
        }
        val lower = url.lowercase(Locale.US)
        val hasVersionSegment = lower.endsWith("/v1") ||
            lower.endsWith("/openai") ||
            lower.contains("/v1beta") ||
            lower.contains("/api/v")
        if (!hasVersionSegment) {
            url = "$url/v1"
        }
        return url
    }

    fun normalizeVideoUrl(raw: String): String {
        val trimmed = raw.trim()
        if (trimmed.isEmpty() || isLocalContentUri(trimmed)) return trimmed

        // Extract first URL if the user pasted a share message containing text + URL
        val urlToken = trimmed.split(Regex("\\s+"))
            .firstOrNull { it.startsWith("http://", true) || it.startsWith("https://", true) }
            ?: trimmed

        val parsed = runCatching { Uri.parse(urlToken) }.getOrNull() ?: return urlToken
        val host = (parsed.host ?: "").lowercase(Locale.US)

        if (host.contains("youtu.be")) {
            val videoId = parsed.pathSegments.firstOrNull()?.takeIf { it.isNotBlank() }
            if (videoId != null) {
                return "https://www.youtube.com/watch?v=$videoId"
            }
        }

        if (host.contains("youtube.com")) {
            val segments = parsed.pathSegments
            if (segments.size >= 2 && (segments[0] == "shorts" || segments[0] == "live" || segments[0] == "embed")) {
                val videoId = segments[1]
                if (videoId.isNotBlank()) {
                    return "https://www.youtube.com/watch?v=$videoId"
                }
            }
            val vParam = parsed.getQueryParameter("v")
            if (!vParam.isNullOrBlank()) {
                return "https://www.youtube.com/watch?v=$vParam"
            }
        }

        if (host.contains("facebook.com") || host.contains("fb.watch")) {
            return urlToken.substringBefore("#")
        }

        return urlToken
    }

    fun isLocalContentUri(raw: String): Boolean {
        val lower = raw.trim().lowercase(Locale.US)
        return lower.startsWith("content://") ||
            lower.startsWith("file://") ||
            lower.startsWith("/storage/") ||
            lower.startsWith("/sdcard/")
    }

    fun formatTimestamp(seconds: Double): String {
        val clamped = seconds.coerceAtLeast(0.0).toLong()
        val hrs = clamped / 3600L
        val mins = (clamped % 3600L) / 60L
        val secs = clamped % 60L
        return if (hrs > 0L) {
            String.format(Locale.US, "%d:%02d:%02d", hrs, mins, secs)
        } else {
            String.format(Locale.US, "%02d:%02d", mins, secs)
        }
    }

    fun formatPreciseTimestamp(seconds: Double): String {
        val safe = seconds.coerceAtLeast(0.0)
        val totalMs = (safe * 1000.0).toLong()
        val hrs = totalMs / 3_600_000L
        val mins = (totalMs % 3_600_000L) / 60_000L
        val secs = (totalMs % 60_000L) / 1000L
        val ms = totalMs % 1000L
        return String.format(Locale.US, "%02d:%02d:%02d.%03d", hrs, mins, secs, ms)
    }

    fun sanitizeFileName(raw: String, maxLen: Int = 48): String {
        val cleaned = raw
            .replace(Regex("[^a-zA-Z0-9._\\- ]"), "")
            .trim()
            .replace(Regex("\\s+"), "_")
        val result = if (cleaned.isBlank()) "clippulse_clip" else cleaned
        return result.take(maxLen)
    }
}
''',

    "app/src/main/java/com/clippulse/app/util/ErrorSanitizer.kt": r'''
package com.clippulse.app.util

import java.util.Locale

object ErrorSanitizer {

    private val secretPatterns = listOf(
        Regex("Bearer\\s+[A-Za-z0-9._\\-+/=]+", RegexOption.IGNORE_CASE),
        Regex("sk-[A-Za-z0-9_\\-]{10,}"),
        Regex("AIza[0-9A-Za-z_\\-]{20,}"),
        Regex("(api[_-]?key|token|authorization)=([^&\\s]+)", RegexOption.IGNORE_CASE)
    )

    fun sanitize(raw: String?, fallback: String = "Unexpected error occurred."): String {
        if (raw.isNullOrBlank()) return fallback
        var cleaned = raw.trim()
        for (pattern in secretPatterns) {
            cleaned = pattern.replace(cleaned, "[REDACTED]")
        }
        val lower = cleaned.lowercase(Locale.US)
        return when {
            lower.contains("sign in to confirm") || lower.contains("confirm you’re not a bot") || lower.contains("cookies") ->
                "Platform requested login verification. Import a fresh cookies.txt in Scan Settings and retry."
            lower.contains("http error 403") || lower.contains("403 forbidden") ->
                "Stream URL expired or blocked (HTTP 403). Re-scan or update yt-dlp engine and retry."
            lower.contains("402") || lower.contains("insufficient") || lower.contains("balance") ->
                "AI key quota or credit exhausted (HTTP 402). Add a backup key or enable Offline Mode."
            lower.contains("401") || lower.contains("invalid api key") || lower.contains("unauthorized") ->
                "Invalid API key (HTTP 401). Check your provider key or switch to Offline Mode."
            lower.contains("429") || lower.contains("rate limit") ->
                "Rate limited (HTTP 429). Key failover attempted; retry in a moment."
            lower.contains("private video") || lower.contains("video unavailable") ->
                "Video is private, deleted, or unavailable in this region."
            lower.contains("unable to resolve host") || lower.contains("failed to connect") ->
                "Network unreachable. Check your internet connection."
            cleaned.length > 260 -> cleaned.take(257) + "..."
            else -> cleaned
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/data/PrefsRepo.kt": r'''
package com.clippulse.app.data

import android.content.Context
import com.clippulse.app.domain.model.AiConfig
import com.clippulse.app.domain.model.AiPreset
import com.clippulse.app.domain.model.ExportRecord
import com.clippulse.app.domain.model.ScanHistoryItem
import com.clippulse.app.domain.model.StoragePreset
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import org.json.JSONArray
import org.json.JSONObject

class PrefsRepo(context: Context) {

    private val prefs = context.getSharedPreferences("clippulse_prefs_v1", Context.MODE_PRIVATE)

    private val _aiConfig = MutableStateFlow(loadAiConfig())
    val aiConfig: StateFlow<AiConfig> = _aiConfig.asStateFlow()

    private val _storagePreset = MutableStateFlow(loadStoragePreset())
    val storagePreset: StateFlow<StoragePreset> = _storagePreset.asStateFlow()

    private val _safTreeUri = MutableStateFlow(prefs.getString(KEY_SAF_URI, "") ?: "")
    val safTreeUri: StateFlow<String> = _safTreeUri.asStateFlow()

    private val _cookiesPath = MutableStateFlow(prefs.getString(KEY_COOKIES_PATH, "") ?: "")
    val cookiesPath: StateFlow<String> = _cookiesPath.asStateFlow()

    private val _scanHistory = MutableStateFlow(loadScanHistory())
    val scanHistory: StateFlow<List<ScanHistoryItem>> = _scanHistory.asStateFlow()

    private val _exportHistory = MutableStateFlow(loadExportHistory())
    val exportHistory: StateFlow<List<ExportRecord>> = _exportHistory.asStateFlow()

    private val _lastEngineUpdateMs = MutableStateFlow(prefs.getLong(KEY_ENGINE_UPDATED_MS, 0L))
    val lastEngineUpdateMs: StateFlow<Long> = _lastEngineUpdateMs.asStateFlow()

    fun saveAiConfig(config: AiConfig) {
        val normalizedKeys = List(4) { idx -> config.apiKeys.getOrElse(idx) { "" } }
        val finalConfig = config.copy(apiKeys = normalizedKeys)
        val keysArr = JSONArray()
        normalizedKeys.forEach { keysArr.put(it) }
        prefs.edit()
            .putString(KEY_AI_PRESET, finalConfig.preset.id)
            .putString(KEY_AI_BASE_URL, finalConfig.baseUrl)
            .putString(KEY_AI_KEYS, keysArr.toString())
            .putInt(KEY_AI_ACTIVE_KEY_IDX, finalConfig.activeKeyIndex)
            .putString(KEY_AI_MODEL, finalConfig.model)
            .putBoolean(KEY_AI_CONNECTED, finalConfig.isConnected)
            .putString(KEY_AI_LAST_MODEL, finalConfig.lastConnectedModel)
            .putBoolean(KEY_AI_OFFLINE, finalConfig.offlineMode)
            .apply()
        _aiConfig.value = finalConfig
    }

    fun setStoragePreset(preset: StoragePreset) {
        prefs.edit().putString(KEY_STORAGE_PRESET, preset.id).apply()
        _storagePreset.value = preset
    }

    fun setSafTreeUri(uriString: String) {
        prefs.edit().putString(KEY_SAF_URI, uriString).apply()
        _safTreeUri.value = uriString
    }

    fun setCookiesPath(path: String) {
        prefs.edit().putString(KEY_COOKIES_PATH, path).apply()
        _cookiesPath.value = path
    }

    fun setLastEngineUpdateMs(timestampMs: Long) {
        prefs.edit().putLong(KEY_ENGINE_UPDATED_MS, timestampMs).apply()
        _lastEngineUpdateMs.value = timestampMs
    }

    fun addScanHistory(item: ScanHistoryItem) {
        val updated = listOf(item) + _scanHistory.value
            .filterNot { it.sourceUrl == item.sourceUrl }
            .take(29)
        saveScanHistory(updated)
    }

    fun removeScanHistory(id: String) {
        saveScanHistory(_scanHistory.value.filterNot { it.id == id })
    }

    fun addExportRecord(record: ExportRecord) {
        val updated = listOf(record) + _exportHistory.value.take(99)
        saveExportHistory(updated)
    }

    fun removeExportRecord(id: String) {
        saveExportHistory(_exportHistory.value.filterNot { it.id == id })
    }

    private fun loadAiConfig(): AiConfig {
        val preset = AiPreset.fromId(prefs.getString(KEY_AI_PRESET, AiPreset.GEMINI_COMPAT.id))
        val baseUrl = prefs.getString(KEY_AI_BASE_URL, preset.defaultBaseUrl) ?: preset.defaultBaseUrl
        val keysRaw = prefs.getString(KEY_AI_KEYS, null)
        val keys = mutableListOf("", "", "", "")
        if (!keysRaw.isNullOrBlank()) {
            runCatching {
                val arr = JSONArray(keysRaw)
                for (i in 0 until minOf(4, arr.length())) {
                    keys[i] = arr.optString(i, "")
                }
            }
        }
        return AiConfig(
            preset = preset,
            baseUrl = baseUrl,
            apiKeys = keys,
            activeKeyIndex = prefs.getInt(KEY_AI_ACTIVE_KEY_IDX, 0).coerceIn(0, 3),
            model = prefs.getString(KEY_AI_MODEL, preset.defaultModel) ?: preset.defaultModel,
            isConnected = prefs.getBoolean(KEY_AI_CONNECTED, false),
            lastConnectedModel = prefs.getString(KEY_AI_LAST_MODEL, "") ?: "",
            offlineMode = prefs.getBoolean(KEY_AI_OFFLINE, false)
        )
    }

    private fun loadStoragePreset(): StoragePreset =
        StoragePreset.fromId(prefs.getString(KEY_STORAGE_PRESET, StoragePreset.MOVIES_CLIPPULSE.id))

    private fun saveScanHistory(items: List<ScanHistoryItem>) {
        val arr = JSONArray()
        items.forEach { item ->
            arr.put(
                JSONObject().apply {
                    put("id", item.id)
                    put("sourceUrl", item.sourceUrl)
                    put("title", item.title)
                    put("uploader", item.uploader)
                    put("durationSec", item.durationSec)
                    put("clipCount", item.clipCount)
                    put("scannedAtMs", item.scannedAtMs)
                    put("isLocalFile", item.isLocalFile)
                }
            )
        }
        prefs.edit().putString(KEY_SCAN_HISTORY, arr.toString()).apply()
        _scanHistory.value = items
    }

    private fun loadScanHistory(): List<ScanHistoryItem> {
        val raw = prefs.getString(KEY_SCAN_HISTORY, null) ?: return emptyList()
        return runCatching {
            val arr = JSONArray(raw)
            buildList {
                for (i in 0 until arr.length()) {
                    val o = arr.optJSONObject(i) ?: continue
                    add(
                        ScanHistoryItem(
                            id = o.optString("id"),
                            sourceUrl = o.optString("sourceUrl"),
                            title = o.optString("title"),
                            uploader = o.optString("uploader"),
                            durationSec = o.optDouble("durationSec", 0.0),
                            clipCount = o.optInt("clipCount", 0),
                            scannedAtMs = o.optLong("scannedAtMs", 0L),
                            isLocalFile = o.optBoolean("isLocalFile", false)
                        )
                    )
                }
            }
        }.getOrDefault(emptyList())
    }

    private fun saveExportHistory(items: List<ExportRecord>) {
        val arr = JSONArray()
        items.forEach { r ->
            arr.put(
                JSONObject().apply {
                    put("id", r.id)
                    put("clipTitle", r.clipTitle)
                    put("sourceTitle", r.sourceTitle)
                    put("durationSec", r.durationSec)
                    put("fileName", r.fileName)
                    put("contentUri", r.contentUri)
                    put("sidecarUri", r.sidecarUri ?: "")
                    put("fileSizeBytes", r.fileSizeBytes)
                    put("createdAtMs", r.createdAtMs)
                    put("aspect9x16", r.aspect9x16)
                }
            )
        }
        prefs.edit().putString(KEY_EXPORT_HISTORY, arr.toString()).apply()
        _exportHistory.value = items
    }

    private fun loadExportHistory(): List<ExportRecord> {
        val raw = prefs.getString(KEY_EXPORT_HISTORY, null) ?: return emptyList()
        return runCatching {
            val arr = JSONArray(raw)
            buildList {
                for (i in 0 until arr.length()) {
                    val o = arr.optJSONObject(i) ?: continue
                    val sidecar = o.optString("sidecarUri", "").ifBlank { null }
                    add(
                        ExportRecord(
                            id = o.optString("id"),
                            clipTitle = o.optString("clipTitle"),
                            sourceTitle = o.optString("sourceTitle"),
                            durationSec = o.optDouble("durationSec", 0.0),
                            fileName = o.optString("fileName"),
                            contentUri = o.optString("contentUri"),
                            sidecarUri = sidecar,
                            fileSizeBytes = o.optLong("fileSizeBytes", 0L),
                            createdAtMs = o.optLong("createdAtMs", 0L),
                            aspect9x16 = o.optBoolean("aspect9x16", true)
                        )
                    )
                }
            }
        }.getOrDefault(emptyList())
    }

    companion object {
        private const val KEY_AI_PRESET = "ai_preset"
        private const val KEY_AI_BASE_URL = "ai_base_url"
        private const val KEY_AI_KEYS = "ai_keys_json"
        private const val KEY_AI_ACTIVE_KEY_IDX = "ai_active_key_idx"
        private const val KEY_AI_MODEL = "ai_model"
        private const val KEY_AI_CONNECTED = "ai_connected"
        private const val KEY_AI_LAST_MODEL = "ai_last_model"
        private const val KEY_AI_OFFLINE = "ai_offline"
        private const val KEY_STORAGE_PRESET = "storage_preset"
        private const val KEY_SAF_URI = "saf_tree_uri"
        private const val KEY_COOKIES_PATH = "cookies_path"
        private const val KEY_SCAN_HISTORY = "scan_history_json"
        private const val KEY_EXPORT_HISTORY = "export_history_json"
        private const val KEY_ENGINE_UPDATED_MS = "engine_updated_ms"
    }
}
''',

    "app/src/main/java/com/clippulse/app/ui/theme/Theme.kt": r'''
package com.clippulse.app.ui.theme

import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Shapes
import androidx.compose.material3.Typography
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.clippulse.app.domain.model.SignalType

object ClipPulseColors {
    val Obsidian = Color(0xFF0B0B0F)
    val Slate = Color(0xFF16161D)
    val Elevated = Color(0xFF1F1F29)
    val Hairline = Color(0xFF262633)

    val Indigo = Color(0xFF6366F1)
    val IndigoMuted = Color(0xFF312E81)

    val CrimsonHeatmap = Color(0xFFEF4444)
    val GoldSuperChat = Color(0xFFF59E0B)
    val PurpleChatHype = Color(0xFFA855F7)
    val CyanAiPick = Color(0xFF06B6D4)
    val EmeraldAudio = Color(0xFF10B981)

    val TextPrimary = Color(0xFFF8FAFC)
    val TextSecondary = Color(0xFF94A3B8)
    val TextMuted = Color(0xFF64748B)
}

object ClipPulseShapes {
    val Card = RoundedCornerShape(16.dp)
    val Chip = RoundedCornerShape(12.dp)
    val Pill = RoundedCornerShape(50)
}

fun signalColor(type: SignalType): Color = when (type) {
    SignalType.HEATMAP -> ClipPulseColors.CrimsonHeatmap
    SignalType.SUPER_CHAT -> ClipPulseColors.GoldSuperChat
    SignalType.CHAT_VELOCITY -> ClipPulseColors.PurpleChatHype
    SignalType.AI_PICK -> ClipPulseColors.CyanAiPick
    SignalType.AUDIO_EXCITEMENT -> ClipPulseColors.EmeraldAudio
}

val MonoTimestampStyle = TextStyle(
    fontFamily = FontFamily.Monospace,
    fontWeight = FontWeight.Medium,
    fontSize = 12.sp,
    letterSpacing = 0.2.sp
)

private val DarkPalette = darkColorScheme(
    primary = ClipPulseColors.Indigo,
    onPrimary = Color.White,
    primaryContainer = ClipPulseColors.IndigoMuted,
    onPrimaryContainer = ClipPulseColors.TextPrimary,
    secondary = ClipPulseColors.CyanAiPick,
    onSecondary = ClipPulseColors.Obsidian,
    tertiary = ClipPulseColors.EmeraldAudio,
    background = ClipPulseColors.Obsidian,
    onBackground = ClipPulseColors.TextPrimary,
    surface = ClipPulseColors.Slate,
    onSurface = ClipPulseColors.TextPrimary,
    surfaceVariant = ClipPulseColors.Elevated,
    onSurfaceVariant = ClipPulseColors.TextSecondary,
    outline = ClipPulseColors.Hairline,
    error = ClipPulseColors.CrimsonHeatmap,
    onError = Color.White
)

private val ClipPulseTypography = Typography(
    titleLarge = TextStyle(
        fontWeight = FontWeight.Bold,
        fontSize = 20.sp,
        lineHeight = 26.sp,
        color = ClipPulseColors.TextPrimary
    ),
    titleMedium = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 16.sp,
        lineHeight = 22.sp,
        color = ClipPulseColors.TextPrimary
    ),
    titleSmall = TextStyle(
        fontWeight = FontWeight.SemiBold,
        fontSize = 14.sp,
        lineHeight = 18.sp,
        color = ClipPulseColors.TextPrimary
    ),
    bodyMedium = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 14.sp,
        lineHeight = 20.sp,
        color = ClipPulseColors.TextPrimary
    ),
    bodySmall = TextStyle(
        fontWeight = FontWeight.Normal,
        fontSize = 12.sp,
        lineHeight = 16.sp,
        color = ClipPulseColors.TextSecondary
    ),
    labelMedium = TextStyle(
        fontWeight = FontWeight.Medium,
        fontSize = 12.sp,
        lineHeight = 16.sp
    )
)

private val MaterialShapes = Shapes(
    small = ClipPulseShapes.Chip,
    medium = ClipPulseShapes.Card,
    large = ClipPulseShapes.Card
)

@Composable
fun ClipPulseTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = DarkPalette,
        typography = ClipPulseTypography,
        shapes = MaterialShapes,
        content = content
    )
}
''',

    "app/src/main/java/com/clippulse/app/AppContainer.kt": r'''
package com.clippulse.app

import android.content.Context
import com.clippulse.app.data.PrefsRepo
import com.clippulse.app.data.ai.AiClient
import com.clippulse.app.data.ai.AiKeyRotator
import com.clippulse.app.data.export.ClipExporter
import com.clippulse.app.data.export.FfmpegRunner
import com.clippulse.app.data.export.SuperChatOverlayRenderer
import com.clippulse.app.data.scan.ScanRepository
import com.clippulse.app.data.scan.YtDlpManager
import com.clippulse.app.data.storage.HistoryRepository
import com.clippulse.app.data.storage.StorageManager
import com.clippulse.app.domain.model.ExportConfig
import com.clippulse.app.domain.model.ExportProgress
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.OkHttpClient
import java.util.concurrent.TimeUnit

class AppContainer(context: Context) {

    val appContext: Context = context.applicationContext

    val okHttpClient: OkHttpClient = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(45, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .retryOnConnectionFailure(true)
        .build()

    val prefsRepo: PrefsRepo = PrefsRepo(appContext)
    val aiKeyRotator: AiKeyRotator = AiKeyRotator(prefsRepo)
    val aiClient: AiClient = AiClient(okHttpClient, prefsRepo, aiKeyRotator)

    val ytDlpManager: YtDlpManager = YtDlpManager(appContext, prefsRepo)
    val scanRepository: ScanRepository = ScanRepository(appContext, ytDlpManager, aiClient, prefsRepo)

    val ffmpegRunner: FfmpegRunner = FfmpegRunner(appContext)
    val overlayRenderer: SuperChatOverlayRenderer = SuperChatOverlayRenderer(appContext)
    val storageManager: StorageManager = StorageManager(appContext, prefsRepo)
    val historyRepository: HistoryRepository = HistoryRepository(prefsRepo)

    val clipExporter: ClipExporter = ClipExporter(
        context = appContext,
        ytDlpManager = ytDlpManager,
        ffmpegRunner = ffmpegRunner,
        overlayRenderer = overlayRenderer,
        storageManager = storageManager,
        historyRepository = historyRepository
    )

    private val _exportProgress = MutableStateFlow<ExportProgress?>(null)
    val exportProgress: StateFlow<ExportProgress?> = _exportProgress.asStateFlow()

    @Volatile
    var pendingExportConfig: ExportConfig? = null

    fun updateExportProgress(progress: ExportProgress?) {
        _exportProgress.value = progress
    }
}
''',
}
