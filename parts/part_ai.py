"""AI client, multi-key failover rotator, streaming JSON parser, ViewModel, and BottomSheet."""

FILES = {
    "app/src/main/java/com/clippulse/app/data/ai/AiKeyRotator.kt": r'''
package com.clippulse.app.data.ai

import com.clippulse.app.data.PrefsRepo
import com.clippulse.app.domain.model.AiConfig

class AiKeyRotator(private val prefsRepo: PrefsRepo) {

    fun isRetryableStatus(httpCode: Int): Boolean {
        return httpCode == 401 ||
            httpCode == 402 ||
            httpCode == 403 ||
            httpCode == 429 ||
            httpCode in 500..599
    }

    fun orderedKeySlots(config: AiConfig): List<Pair<Int, String>> {
        val usable = config.usableKeys()
        if (usable.isEmpty()) return emptyList()
        val startIdx = usable.indexOfFirst { it.first == config.activeKeyIndex }.takeIf { it >= 0 } ?: 0
        return buildList(usable.size) {
            for (offset in usable.indices) {
                add(usable[(startIdx + offset) % usable.size])
            }
        }
    }

    fun markKeyActive(slotIndex: Int) {
        val current = prefsRepo.aiConfig.value
        if (current.activeKeyIndex != slotIndex) {
            prefsRepo.saveAiConfig(current.copy(activeKeyIndex = slotIndex.coerceIn(0, 3)))
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/data/ai/StreamingJsonParser.kt": r'''
package com.clippulse.app.data.ai

import android.util.JsonReader
import android.util.JsonToken
import com.clippulse.app.domain.model.Signal
import com.clippulse.app.domain.model.SignalType
import com.clippulse.app.domain.model.ViralCopyPack
import java.io.InputStream
import java.io.InputStreamReader
import java.io.StringReader
import java.nio.charset.StandardCharsets

object StreamingJsonParser {

    fun parseModelsStream(inputStream: InputStream): List<String> {
        val models = mutableListOf<String>()
        JsonReader(InputStreamReader(inputStream, StandardCharsets.UTF_8)).use { reader ->
            reader.isLenient = true
            if (reader.peek() != JsonToken.BEGIN_OBJECT) return emptyList()
            reader.beginObject()
            while (reader.hasNext()) {
                when (reader.nextName()) {
                    "data" -> {
                        if (reader.peek() == JsonToken.BEGIN_ARRAY) {
                            reader.beginArray()
                            while (reader.hasNext()) {
                                if (reader.peek() == JsonToken.BEGIN_OBJECT) {
                                    var id: String? = null
                                    reader.beginObject()
                                    while (reader.hasNext()) {
                                        if (reader.nextName() == "id" && reader.peek() == JsonToken.STRING) {
                                            id = reader.nextString()
                                        } else {
                                            reader.skipValue()
                                        }
                                    }
                                    reader.endObject()
                                    if (!id.isNullOrBlank()) models.add(id)
                                } else {
                                    reader.skipValue()
                                }
                            }
                            reader.endArray()
                        } else {
                            reader.skipValue()
                        }
                    }
                    else -> reader.skipValue()
                }
            }
            reader.endObject()
        }
        return models.distinct().sorted()
    }

    fun parseChatCompletionContent(inputStream: InputStream): String {
        var content = ""
        JsonReader(InputStreamReader(inputStream, StandardCharsets.UTF_8)).use { reader ->
            reader.isLenient = true
            if (reader.peek() != JsonToken.BEGIN_OBJECT) return ""
            reader.beginObject()
            while (reader.hasNext()) {
                when (reader.nextName()) {
                    "choices" -> {
                        if (reader.peek() == JsonToken.BEGIN_ARRAY) {
                            reader.beginArray()
                            while (reader.hasNext()) {
                                if (content.isEmpty() && reader.peek() == JsonToken.BEGIN_OBJECT) {
                                    content = readChoiceMessageContent(reader)
                                } else {
                                    reader.skipValue()
                                }
                            }
                            reader.endArray()
                        } else {
                            reader.skipValue()
                        }
                    }
                    else -> reader.skipValue()
                }
            }
            reader.endObject()
        }
        return content.trim()
    }

    private fun readChoiceMessageContent(reader: JsonReader): String {
        var text = ""
        reader.beginObject()
        while (reader.hasNext()) {
            when (reader.nextName()) {
                "message" -> {
                    if (reader.peek() == JsonToken.BEGIN_OBJECT) {
                        reader.beginObject()
                        while (reader.hasNext()) {
                            if (reader.nextName() == "content" && reader.peek() == JsonToken.STRING) {
                                text = reader.nextString()
                            } else {
                                reader.skipValue()
                            }
                        }
                        reader.endObject()
                    } else {
                        reader.skipValue()
                    }
                }
                "text" -> {
                    if (reader.peek() == JsonToken.STRING) {
                        text = reader.nextString()
                    } else {
                        reader.skipValue()
                    }
                }
                else -> reader.skipValue()
            }
        }
        reader.endObject()
        return text
    }

    fun extractJsonBlock(raw: String): String {
        val cleaned = raw.trim()
            .removePrefix("```json")
            .removePrefix("```JSON")
            .removePrefix("```")
            .removeSuffix("```")
            .trim()
        val firstObj = cleaned.indexOf('{')
        val firstArr = cleaned.indexOf('[')
        val start = when {
            firstObj >= 0 && firstArr >= 0 -> minOf(firstObj, firstArr)
            firstObj >= 0 -> firstObj
            firstArr >= 0 -> firstArr
            else -> return cleaned
        }
        val openChar = cleaned[start]
        val closeChar = if (openChar == '{') '}' else ']'
        val end = cleaned.lastIndexOf(closeChar)
        return if (end > start) cleaned.substring(start, end + 1) else cleaned.substring(start)
    }

    fun parseAiSignals(rawText: String, maxDurationSec: Double): List<Signal> {
        val json = extractJsonBlock(rawText)
        val signals = mutableListOf<Signal>()
        runCatching {
            JsonReader(StringReader(json)).use { reader ->
                reader.isLenient = true
                when (reader.peek()) {
                    JsonToken.BEGIN_ARRAY -> readSignalsArray(reader, maxDurationSec, signals)
                    JsonToken.BEGIN_OBJECT -> {
                        reader.beginObject()
                        while (reader.hasNext()) {
                            val name = reader.nextName()
                            if ((name == "clips" || name == "picks" || name == "signals") &&
                                reader.peek() == JsonToken.BEGIN_ARRAY
                            ) {
                                readSignalsArray(reader, maxDurationSec, signals)
                            } else {
                                reader.skipValue()
                            }
                        }
                        reader.endObject()
                    }
                    else -> Unit
                }
            }
        }
        return signals
    }

    private fun readSignalsArray(
        reader: JsonReader,
        maxDurationSec: Double,
        out: MutableList<Signal>
    ) {
        reader.beginArray()
        while (reader.hasNext()) {
            if (reader.peek() != JsonToken.BEGIN_OBJECT) {
                reader.skipValue()
                continue
            }
            var start = -1.0
            var end = -1.0
            var score = 0.85
            var title = "AI Viral Pick"
            var reason = "High retention hook"
            reader.beginObject()
            while (reader.hasNext()) {
                when (reader.nextName()) {
                    "start", "start_sec", "startSec" -> start = readNumberSafe(reader, -1.0)
                    "end", "end_sec", "endSec" -> end = readNumberSafe(reader, -1.0)
                    "score" -> score = readNumberSafe(reader, 0.85)
                    "title", "label" -> title = readStringSafe(reader, title)
                    "reason", "hook", "meta" -> reason = readStringSafe(reader, reason)
                    else -> reader.skipValue()
                }
            }
            reader.endObject()
            if (start >= 0.0 && end > start + 4.0) {
                val clampedStart = start.coerceIn(0.0, maxDurationSec.coerceAtLeast(1.0))
                val clampedEnd = end.coerceIn(clampedStart + 5.0, maxDurationSec.coerceAtLeast(clampedStart + 5.0))
                val normScore = if (score > 1.0) (score / 100.0).coerceIn(0.1, 1.0) else score.coerceIn(0.1, 1.0)
                out.add(
                    Signal(
                        start = clampedStart,
                        end = clampedEnd,
                        score = normScore,
                        type = SignalType.AI_PICK,
                        label = title,
                        meta = reason
                    )
                )
            }
        }
        reader.endArray()
    }

    fun parseViralCopyPack(rawText: String): ViralCopyPack? {
        val json = extractJsonBlock(rawText)
        return runCatching {
            val titles = mutableListOf<String>()
            var hook = ""
            var description = ""
            val hashtags = mutableListOf<String>()
            JsonReader(StringReader(json)).use { reader ->
                reader.isLenient = true
                if (reader.peek() != JsonToken.BEGIN_OBJECT) return null
                reader.beginObject()
                while (reader.hasNext()) {
                    when (reader.nextName()) {
                        "titles" -> readStringArray(reader, titles)
                        "hook" -> hook = readStringSafe(reader, "")
                        "description" -> description = readStringSafe(reader, "")
                        "hashtags" -> readStringArray(reader, hashtags)
                        else -> reader.skipValue()
                    }
                }
                reader.endObject()
            }
            if (titles.isEmpty() && hook.isBlank() && description.isBlank()) {
                null
            } else {
                ViralCopyPack(
                    titles = titles.ifEmpty { listOf("Unmissable Highlight") },
                    hook = hook.ifBlank { "Wait for the twist in this clip." },
                    description = description.ifBlank { "Clipped with ClipPulse." },
                    hashtags = hashtags.ifEmpty { listOf("#shorts", "#viral", "#highlights") }
                )
            }
        }.getOrNull()
    }

    private fun readStringArray(reader: JsonReader, target: MutableList<String>) {
        if (reader.peek() != JsonToken.BEGIN_ARRAY) {
            reader.skipValue()
            return
        }
        reader.beginArray()
        while (reader.hasNext()) {
            val item = readStringSafe(reader, "")
            if (item.isNotBlank()) target.add(item)
        }
        reader.endArray()
    }

    private fun readStringSafe(reader: JsonReader, fallback: String): String {
        return when (reader.peek()) {
            JsonToken.STRING -> reader.nextString()
            JsonToken.NUMBER -> reader.nextString()
            else -> {
                reader.skipValue()
                fallback
            }
        }
    }

    private fun readNumberSafe(reader: JsonReader, fallback: Double): Double {
        return when (reader.peek()) {
            JsonToken.NUMBER -> reader.nextDouble()
            JsonToken.STRING -> reader.nextString().toDoubleOrNull() ?: fallback
            else -> {
                reader.skipValue()
                fallback
            }
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/data/ai/AiClient.kt": r'''
package com.clippulse.app.data.ai

import com.clippulse.app.data.PrefsRepo
import com.clippulse.app.domain.model.AiConfig
import com.clippulse.app.domain.model.AppResult
import com.clippulse.app.domain.model.ClipCandidate
import com.clippulse.app.domain.model.Signal
import com.clippulse.app.domain.model.VideoMetadata
import com.clippulse.app.domain.model.ViralCopyPack
import com.clippulse.app.util.ErrorSanitizer
import com.clippulse.app.util.UrlNormalizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

class AiClient(
    private val okHttpClient: OkHttpClient,
    private val prefsRepo: PrefsRepo,
    private val keyRotator: AiKeyRotator
) {

    private val jsonMediaType = "application/json; charset=utf-8".toMediaType()

    suspend fun fetchModels(config: AiConfig): AppResult<List<String>> = withContext(Dispatchers.IO) {
        if (config.offlineMode) {
            return@withContext AppResult.Error("Offline Mode is enabled. Disable it to fetch remote models.")
        }
        val baseUrl = UrlNormalizer.normalizeAiBaseUrl(config.baseUrl)
        val slots = keyRotator.orderedKeySlots(config)
        if (slots.isEmpty()) {
            return@withContext AppResult.Error("Add at least one API key first.")
        }

        var lastError = "Unable to fetch models."
        var lastCode: Int? = null
        for ((slotIdx, key) in slots) {
            val req = Request.Builder()
                .url("$baseUrl/models")
                .header("Authorization", "Bearer $key")
                .header("Accept", "application/json")
                .get()
                .build()
            try {
                okHttpClient.newCall(req).execute().use { resp ->
                    val code = resp.code
                    if (resp.isSuccessful) {
                        val stream = resp.body?.byteStream()
                        val models = if (stream != null) {
                            StreamingJsonParser.parseModelsStream(stream)
                        } else {
                            emptyList()
                        }
                        keyRotator.markKeyActive(slotIdx)
                        return@withContext if (models.isNotEmpty()) {
                            AppResult.Success(models)
                        } else {
                            AppResult.Error("Endpoint returned 0 models. Enter a model ID manually.")
                        }
                    } else {
                        val errBody = resp.body?.string().orEmpty()
                        lastCode = code
                        lastError = ErrorSanitizer.sanitize("HTTP $code: $errBody")
                        if (!keyRotator.isRetryableStatus(code)) {
                            return@withContext AppResult.Error(lastError, code)
                        }
                    }
                }
            } catch (e: Exception) {
                lastError = ErrorSanitizer.sanitize(e.message, "Network error while listing models.")
            }
        }
        AppResult.Error(lastError, lastCode)
    }

    suspend fun testConnection(config: AiConfig): AppResult<String> = withContext(Dispatchers.IO) {
        if (config.offlineMode) {
            return@withContext AppResult.Success("Offline heuristic engine active")
        }
        val model = config.model.trim().ifEmpty { config.preset.defaultModel }
        val result = chatCompletion(
            config = config.copy(model = model),
            systemPrompt = "You are a health-check responder.",
            userPrompt = "Reply with OK.",
            maxTokens = 16,
            temperature = 0.0
        )
        when (result) {
            is AppResult.Success -> {
                val normalized = UrlNormalizer.normalizeAiBaseUrl(config.baseUrl)
                prefsRepo.saveAiConfig(
                    config.copy(
                        baseUrl = normalized,
                        model = model,
                        isConnected = true,
                        lastConnectedModel = model
                    )
                )
                AppResult.Success("Connected ($model)")
            }
            is AppResult.Error -> {
                prefsRepo.saveAiConfig(config.copy(isConnected = false))
                result
            }
        }
    }

    suspend fun detectAiPicks(
        metadata: VideoMetadata,
        transcriptContext: String
    ): AppResult<List<Signal>> = withContext(Dispatchers.IO) {
        val config = prefsRepo.aiConfig.value
        if (config.offlineMode || !config.isConnected || config.usableKeys().isEmpty()) {
            return@withContext AppResult.Success(emptyList())
        }
        if (transcriptContext.isBlank()) {
            return@withContext AppResult.Success(emptyList())
        }

        val trimmedTranscript = transcriptContext.take(6000)
        val systemPrompt =
            "You are a viral short-form video editor. Identify up to 4 standout 15-55 second moments. " +
                "Return strict JSON only: {\"clips\":[{\"start\":12.0,\"end\":42.0,\"score\":0.92,\"title\":\"Short punchy title\",\"reason\":\"Why it hooks viewers\"}]}"
        val userPrompt = buildString {
            append("Video: ").append(metadata.title).append('\n')
            append(String.format(Locale.US, "Duration: %.1fs\n", metadata.durationSec))
            append("Timestamped transcript:\n")
            append(trimmedTranscript)
        }

        when (val res = chatCompletion(config, systemPrompt, userPrompt, maxTokens = 512, temperature = 0.3)) {
            is AppResult.Success -> {
                val signals = StreamingJsonParser.parseAiSignals(res.data, metadata.durationSec)
                AppResult.Success(signals)
            }
            is AppResult.Error -> res
        }
    }

    suspend fun generateViralCopyPack(
        clip: ClipCandidate,
        metadata: VideoMetadata
    ): AppResult<ViralCopyPack> = withContext(Dispatchers.IO) {
        val config = prefsRepo.aiConfig.value
        if (config.offlineMode || config.usableKeys().isEmpty()) {
            return@withContext AppResult.Success(buildOfflineCopyPack(clip, metadata))
        }

        val systemPrompt =
            "You generate YouTube Shorts and Reels metadata. Return strict JSON only: " +
                "{\"titles\":[\"Title 1\",\"Title 2\",\"Title 3\"],\"hook\":\"First 3s spoken/on-screen hook\"," +
                "\"description\":\"2 concise sentences\",\"hashtags\":[\"#tag1\",\"#tag2\",\"#tag3\",\"#tag4\",\"#tag5\"]}"
        val userPrompt = buildString {
            append("Source Title: ").append(metadata.title).append('\n')
            append("Uploader: ").append(metadata.uploader).append('\n')
            append("Clip Title: ").append(clip.title).append('\n')
            append("Signal Reason: ").append(clip.reason).append('\n')
            append(
                String.format(
                    Locale.US,
                    "Window: %.1fs to %.1fs (%.1fs)\n",
                    clip.startSec,
                    clip.endSec,
                    clip.durationSec
                )
            )
            clip.superChat?.let { sc ->
                append("Super Chat: ").append(sc.author).append(" (").append(sc.amountText).append("): ")
                    .append(sc.message).append('\n')
            }
            if (metadata.transcriptSnippet.isNotBlank()) {
                append("Context: ").append(metadata.transcriptSnippet.take(1200))
            }
        }

        when (val res = chatCompletion(config, systemPrompt, userPrompt, maxTokens = 380, temperature = 0.6)) {
            is AppResult.Success -> {
                val parsed = StreamingJsonParser.parseViralCopyPack(res.data)
                    ?: buildOfflineCopyPack(clip, metadata)
                AppResult.Success(parsed)
            }
            is AppResult.Error -> AppResult.Success(buildOfflineCopyPack(clip, metadata))
        }
    }

    fun buildOfflineCopyPack(clip: ClipCandidate, metadata: VideoMetadata): ViralCopyPack {
        val cleanSource = metadata.title.take(55).ifBlank { "Live Stream Highlight" }
        val signalTag = when (clip.primarySignal.name) {
            "SUPER_CHAT" -> "#superchat"
            "HEATMAP" -> "#mostreplayed"
            "CHAT_VELOCITY" -> "#chatgoingwild"
            else -> "#highlights"
        }
        val scLine = clip.superChat?.let { " (${it.amountText} from ${it.author})" } ?: ""
        return ViralCopyPack(
            titles = listOf(
                "${clip.title}$scLine",
                "Wait Until You See This Moment - $cleanSource",
                "Peak Reaction in ${clip.durationSec.toInt()} Seconds"
            ),
            hook = clip.superChat?.let { "${it.author} just dropped ${it.amountText} and changed the stream." }
                ?: "Watch closely — the peak moment hits right here.",
            description = "${clip.reason}. Highlight clipped from $cleanSource (${UrlNormalizer.formatTimestamp(clip.startSec)} - ${UrlNormalizer.formatTimestamp(clip.endSec)}).",
            hashtags = listOf("#shorts", "#reels", "#viral", signalTag, "#clippulse")
        )
    }

    suspend fun chatCompletion(
        config: AiConfig,
        systemPrompt: String,
        userPrompt: String,
        maxTokens: Int,
        temperature: Double
    ): AppResult<String> = withContext(Dispatchers.IO) {
        val baseUrl = UrlNormalizer.normalizeAiBaseUrl(config.baseUrl)
        val slots = keyRotator.orderedKeySlots(config)
        if (slots.isEmpty()) {
            return@withContext AppResult.Error("No API keys configured. Add a key or enable Offline Mode.")
        }

        val payload = JSONObject().apply {
            put("model", config.model.trim().ifEmpty { config.preset.defaultModel })
            put("max_tokens", maxTokens)
            put("temperature", temperature)
            put(
                "messages",
                JSONArray().apply {
                    put(JSONObject().put("role", "system").put("content", systemPrompt))
                    put(JSONObject().put("role", "user").put("content", userPrompt))
                }
            )
        }.toString()

        var lastError = "AI request failed across all configured keys."
        var lastCode: Int? = null

        for ((slotIdx, key) in slots) {
            val req = Request.Builder()
                .url("$baseUrl/chat/completions")
                .header("Authorization", "Bearer $key")
                .header("Content-Type", "application/json")
                .header("Accept", "application/json")
                .post(payload.toRequestBody(jsonMediaType))
                .build()

            try {
                okHttpClient.newCall(req).execute().use { resp ->
                    val code = resp.code
                    if (resp.isSuccessful) {
                        val stream = resp.body?.byteStream()
                        val content = if (stream != null) {
                            StreamingJsonParser.parseChatCompletionContent(stream)
                        } else {
                            ""
                        }
                        keyRotator.markKeyActive(slotIdx)
                        return@withContext AppResult.Success(content)
                    } else {
                        val errBody = resp.body?.string().orEmpty()
                        lastCode = code
                        lastError = ErrorSanitizer.sanitize("HTTP $code: $errBody")
                        if (!keyRotator.isRetryableStatus(code)) {
                            return@withContext AppResult.Error(lastError, code)
                        }
                    }
                }
            } catch (e: Exception) {
                lastError = ErrorSanitizer.sanitize(e.message, "Network error calling AI provider.")
            }
        }
        AppResult.Error(lastError, lastCode)
    }
}
''',

    "app/src/main/java/com/clippulse/app/viewmodel/AiSettingsViewModel.kt": r'''
package com.clippulse.app.viewmodel

import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.clippulse.app.data.PrefsRepo
import com.clippulse.app.data.ai.AiClient
import com.clippulse.app.domain.model.AiConfig
import com.clippulse.app.domain.model.AiPreset
import com.clippulse.app.domain.model.AppResult
import com.clippulse.app.util.UrlNormalizer
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch

data class AiSettingsUiState(
    val config: AiConfig = AiConfig(),
    val availableModels: List<String> = emptyList(),
    val isFetchingModels: Boolean = false,
    val isTestingConnection: Boolean = false,
    val statusMessage: String? = null,
    val errorMessage: String? = null
)

class AiSettingsViewModel(
    private val prefsRepo: PrefsRepo,
    private val aiClient: AiClient
) : ViewModel() {

    private val _uiState = MutableStateFlow(AiSettingsUiState(config = prefsRepo.aiConfig.value))
    val uiState: StateFlow<AiSettingsUiState> = _uiState.asStateFlow()

    private var activeJob: Job? = null

    init {
        viewModelScope.launch {
            prefsRepo.aiConfig.collect { saved ->
                _uiState.update { it.copy(config = saved) }
            }
        }
    }

    fun selectPreset(preset: AiPreset) {
        val current = _uiState.value.config
        val updated = current.copy(
            preset = preset,
            baseUrl = preset.defaultBaseUrl,
            model = preset.defaultModel,
            isConnected = false
        )
        prefsRepo.saveAiConfig(updated)
        _uiState.update { it.copy(statusMessage = null, errorMessage = null, availableModels = emptyList()) }
    }

    fun updateBaseUrl(url: String) {
        val updated = _uiState.value.config.copy(baseUrl = url, isConnected = false)
        prefsRepo.saveAiConfig(updated)
    }

    fun updateApiKey(slotIndex: Int, key: String) {
        val current = _uiState.value.config
        val nextKeys = current.apiKeys.toMutableList()
        while (nextKeys.size < 4) nextKeys.add("")
        if (slotIndex in 0..3) {
            nextKeys[slotIndex] = key
        }
        prefsRepo.saveAiConfig(current.copy(apiKeys = nextKeys, isConnected = false))
    }

    fun updateModel(model: String) {
        val updated = _uiState.value.config.copy(model = model)
        prefsRepo.saveAiConfig(updated)
    }

    fun toggleOfflineMode(enabled: Boolean) {
        val updated = _uiState.value.config.copy(offlineMode = enabled)
        prefsRepo.saveAiConfig(updated)
        _uiState.update {
            it.copy(
                statusMessage = if (enabled) "Offline Mode enabled — local engines only" else null,
                errorMessage = null
            )
        }
    }

    fun fetchModels() {
        activeJob?.cancel()
        val current = _uiState.value.config
        val normalized = UrlNormalizer.normalizeAiBaseUrl(current.baseUrl)
        val updated = current.copy(baseUrl = normalized)
        prefsRepo.saveAiConfig(updated)

        activeJob = viewModelScope.launch {
            _uiState.update { it.copy(isFetchingModels = true, errorMessage = null, statusMessage = null) }
            when (val res = aiClient.fetchModels(updated)) {
                is AppResult.Success -> {
                    val models = res.data
                    val chosen = if (updated.model in models) updated.model else models.firstOrNull() ?: updated.model
                    prefsRepo.saveAiConfig(updated.copy(model = chosen))
                    _uiState.update {
                        it.copy(
                            isFetchingModels = false,
                            availableModels = models,
                            statusMessage = "Loaded ${models.size} models"
                        )
                    }
                }
                is AppResult.Error -> {
                    _uiState.update {
                        it.copy(
                            isFetchingModels = false,
                            errorMessage = res.message
                        )
                    }
                }
            }
        }
    }

    fun testConnection() {
        activeJob?.cancel()
        val current = _uiState.value.config
        val normalized = UrlNormalizer.normalizeAiBaseUrl(current.baseUrl)
        val updated = current.copy(baseUrl = normalized)
        prefsRepo.saveAiConfig(updated)

        activeJob = viewModelScope.launch {
            _uiState.update { it.copy(isTestingConnection = true, errorMessage = null, statusMessage = null) }
            when (val res = aiClient.testConnection(updated)) {
                is AppResult.Success -> {
                    _uiState.update {
                        it.copy(
                            isTestingConnection = false,
                            statusMessage = res.data,
                            errorMessage = null
                        )
                    }
                }
                is AppResult.Error -> {
                    _uiState.update {
                        it.copy(
                            isTestingConnection = false,
                            errorMessage = res.message
                        )
                    }
                }
            }
        }
    }

    class Factory(
        private val prefsRepo: PrefsRepo,
        private val aiClient: AiClient
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return AiSettingsViewModel(prefsRepo, aiClient) as T
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/ui/ai/AiManagerBottomSheet.kt": r'''
package com.clippulse.app.ui.ai

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Bolt
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.filled.CloudOff
import androidx.compose.material.icons.filled.KeyboardArrowDown
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Visibility
import androidx.compose.material.icons.filled.VisibilityOff
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.OutlinedTextFieldDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.PasswordVisualTransformation
import androidx.compose.ui.text.input.VisualTransformation
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.clippulse.app.domain.model.AiPreset
import com.clippulse.app.ui.theme.ClipPulseColors
import com.clippulse.app.ui.theme.ClipPulseShapes
import com.clippulse.app.viewmodel.AiSettingsViewModel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AiManagerBottomSheet(
    viewModel: AiSettingsViewModel,
    onDismiss: () -> Unit
) {
    val state by viewModel.uiState.collectAsStateWithLifecycle()
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var revealKeys by remember { mutableStateOf(false) }
    var modelDropdownExpanded by remember { mutableStateOf(false) }

    ModalBottomSheet(
        onDismissRequest = onDismiss,
        sheetState = sheetState,
        containerColor = ClipPulseColors.Slate,
        contentColor = ClipPulseColors.TextPrimary
    ) {
        Column(
            modifier = Modifier
                .fillMaxWidth()
                .verticalScroll(rememberScrollState())
                .padding(horizontal = 20.dp)
                .padding(bottom = 28.dp),
            verticalArrangement = Arrangement.spacedBy(14.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column {
                    Text(
                        text = "AI Provider Manager",
                        style = MaterialTheme.typography.titleLarge
                    )
                    Text(
                        text = "Multi-key failover (401/402/403/429/5xx)",
                        style = MaterialTheme.typography.bodySmall
                    )
                }
                AiStatusPill(
                    offlineMode = state.config.offlineMode,
                    isConnected = state.config.isConnected,
                    model = state.config.lastConnectedModel
                )
            }

            Surface(
                shape = ClipPulseShapes.Card,
                color = ClipPulseColors.Elevated,
                border = BorderStroke(1.dp, ClipPulseColors.Hairline)
            ) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 14.dp, vertical = 10.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically
                ) {
                    Column(modifier = Modifier.weight(1f)) {
                        Text(
                            text = "Offline Mode",
                            style = MaterialTheme.typography.titleSmall
                        )
                        Text(
                            text = "Use local Heatmap, Super Chat, Chat Velocity & Transcript engines only",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    Switch(
                        checked = state.config.offlineMode,
                        onCheckedChange = viewModel::toggleOfflineMode,
                        colors = SwitchDefaults.colors(
                            checkedThumbColor = Color.White,
                            checkedTrackColor = ClipPulseColors.Indigo
                        )
                    )
                }
            }

            Text(
                text = "Provider Presets",
                style = MaterialTheme.typography.titleSmall
            )
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)
            ) {
                AiPreset.entries.forEach { preset ->
                    val selected = state.config.preset == preset
                    FilterChip(
                        selected = selected,
                        onClick = { viewModel.selectPreset(preset) },
                        label = { Text(preset.displayName) },
                        shape = ClipPulseShapes.Chip,
                        colors = FilterChipDefaults.filterChipColors(
                            selectedContainerColor = ClipPulseColors.Indigo,
                            selectedLabelColor = Color.White,
                            containerColor = ClipPulseColors.Elevated,
                            labelColor = ClipPulseColors.TextSecondary
                        ),
                        border = FilterChipDefaults.filterChipBorder(
                            enabled = true,
                            selected = selected,
                            borderColor = ClipPulseColors.Hairline,
                            selectedBorderColor = ClipPulseColors.Indigo
                        )
                    )
                }
            }

            OutlinedTextField(
                value = state.config.baseUrl,
                onValueChange = viewModel::updateBaseUrl,
                label = { Text("Base URL (auto-normalized)") },
                singleLine = true,
                enabled = !state.config.offlineMode,
                modifier = Modifier.fillMaxWidth(),
                shape = ClipPulseShapes.Chip,
                colors = textFieldColors()
            )

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "API Keys (Primary + 3 Backups)",
                    style = MaterialTheme.typography.titleSmall
                )
                IconButton(
                    onClick = { revealKeys = !revealKeys },
                    modifier = Modifier.size(48.dp)
                ) {
                    Icon(
                        imageVector = if (revealKeys) Icons.Default.VisibilityOff else Icons.Default.Visibility,
                        contentDescription = "Toggle API key visibility",
                        tint = ClipPulseColors.TextSecondary
                    )
                }
            }

            val slotLabels = listOf("Primary Key (Slot 1)", "Backup Key (Slot 2)", "Backup Key (Slot 3)", "Backup Key (Slot 4)")
            slotLabels.forEachIndexed { idx, label ->
                val isActive = state.config.activeKeyIndex == idx && state.config.apiKeys.getOrElse(idx) { "" }.isNotBlank()
                OutlinedTextField(
                    value = state.config.apiKeys.getOrElse(idx) { "" },
                    onValueChange = { viewModel.updateApiKey(idx, it) },
                    label = {
                        Text(if (isActive) "$label • Active" else label)
                    },
                    singleLine = true,
                    enabled = !state.config.offlineMode,
                    visualTransformation = if (revealKeys) VisualTransformation.None else PasswordVisualTransformation(),
                    modifier = Modifier.fillMaxWidth(),
                    shape = ClipPulseShapes.Chip,
                    colors = textFieldColors()
                )
            }

            Box(modifier = Modifier.fillMaxWidth()) {
                OutlinedTextField(
                    value = state.config.model,
                    onValueChange = viewModel::updateModel,
                    label = { Text("Model ID") },
                    singleLine = true,
                    enabled = !state.config.offlineMode,
                    trailingIcon = {
                        if (state.availableModels.isNotEmpty()) {
                            IconButton(
                                onClick = { modelDropdownExpanded = true },
                                modifier = Modifier.size(48.dp)
                            ) {
                                Icon(
                                    imageVector = Icons.Default.KeyboardArrowDown,
                                    contentDescription = "Choose fetched model",
                                    tint = ClipPulseColors.TextSecondary
                                )
                            }
                        }
                    },
                    modifier = Modifier.fillMaxWidth(),
                    shape = ClipPulseShapes.Chip,
                    colors = textFieldColors()
                )
                DropdownMenu(
                    expanded = modelDropdownExpanded,
                    onDismissRequest = { modelDropdownExpanded = false },
                    modifier = Modifier
                        .background(ClipPulseColors.Elevated)
                        .heightIn(max = 260.dp)
                ) {
                    state.availableModels.forEach { modelId ->
                        DropdownMenuItem(
                            text = { Text(modelId, color = ClipPulseColors.TextPrimary) },
                            onClick = {
                                viewModel.updateModel(modelId)
                                modelDropdownExpanded = false
                            }
                        )
                    }
                }
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(10.dp)
            ) {
                OutlinedButton(
                    onClick = viewModel::fetchModels,
                    enabled = !state.config.offlineMode && !state.isFetchingModels && !state.isTestingConnection,
                    shape = ClipPulseShapes.Chip,
                    border = BorderStroke(1.dp, ClipPulseColors.Hairline),
                    modifier = Modifier
                        .weight(1f)
                        .height(48.dp)
                ) {
                    if (state.isFetchingModels) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            strokeWidth = 2.dp,
                            color = ClipPulseColors.CyanAiPick
                        )
                    } else {
                        Icon(Icons.Default.Refresh, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Fetch Models")
                    }
                }

                Button(
                    onClick = viewModel::testConnection,
                    enabled = !state.isTestingConnection && !state.isFetchingModels,
                    shape = ClipPulseShapes.Chip,
                    colors = ButtonDefaults.buttonColors(containerColor = ClipPulseColors.Indigo),
                    modifier = Modifier
                        .weight(1f)
                        .height(48.dp)
                ) {
                    if (state.isTestingConnection) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(18.dp),
                            strokeWidth = 2.dp,
                            color = Color.White
                        )
                    } else {
                        Icon(Icons.Default.Bolt, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(Modifier.width(6.dp))
                        Text("Connect Probe")
                    }
                }
            }

            state.statusMessage?.let { msg ->
                Surface(
                    shape = ClipPulseShapes.Chip,
                    color = ClipPulseColors.EmeraldAudio.copy(alpha = 0.14f),
                    border = BorderStroke(1.dp, ClipPulseColors.EmeraldAudio.copy(alpha = 0.45f)),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        text = msg,
                        color = ClipPulseColors.EmeraldAudio,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(12.dp)
                    )
                }
            }

            state.errorMessage?.let { err ->
                Surface(
                    shape = ClipPulseShapes.Chip,
                    color = ClipPulseColors.CrimsonHeatmap.copy(alpha = 0.14f),
                    border = BorderStroke(1.dp, ClipPulseColors.CrimsonHeatmap.copy(alpha = 0.45f)),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        text = err,
                        color = ClipPulseColors.CrimsonHeatmap,
                        style = MaterialTheme.typography.bodySmall,
                        modifier = Modifier.padding(12.dp)
                    )
                }
            }
        }
    }
}

@Composable
fun AiStatusPill(
    offlineMode: Boolean,
    isConnected: Boolean,
    model: String,
    onClick: (() -> Unit)? = null
) {
    val bgColor = when {
        offlineMode -> ClipPulseColors.Elevated
        isConnected -> ClipPulseColors.EmeraldAudio.copy(alpha = 0.16f)
        else -> ClipPulseColors.Elevated
    }
    val borderColor = when {
        offlineMode -> ClipPulseColors.Hairline
        isConnected -> ClipPulseColors.EmeraldAudio
        else -> ClipPulseColors.Hairline
    }
    val contentColor = when {
        offlineMode -> ClipPulseColors.TextSecondary
        isConnected -> ClipPulseColors.EmeraldAudio
        else -> ClipPulseColors.TextSecondary
    }
    val label = when {
        offlineMode -> "Offline"
        isConnected -> if (model.isNotBlank()) "AI: ${model.take(14)}" else "AI Ready"
        else -> "AI Setup"
    }

    Row(
        modifier = Modifier
            .background(bgColor, ClipPulseShapes.Pill)
            .border(1.dp, borderColor, ClipPulseShapes.Pill)
            .let { mod -> if (onClick != null) mod.clickable(onClick = onClick) else mod }
            .padding(horizontal = 12.dp, vertical = 7.dp),
        verticalAlignment = Alignment.CenterVertically,
        horizontalArrangement = Arrangement.spacedBy(5.dp)
    ) {
        Icon(
            imageVector = when {
                offlineMode -> Icons.Default.CloudOff
                isConnected -> Icons.Default.CheckCircle
                else -> Icons.Default.Bolt
            },
            contentDescription = null,
            tint = contentColor,
            modifier = Modifier.size(14.dp)
        )
        Text(
            text = label,
            color = contentColor,
            style = MaterialTheme.typography.labelMedium,
            fontWeight = FontWeight.SemiBold
        )
    }
}

@Composable
private fun textFieldColors() = OutlinedTextFieldDefaults.colors(
    focusedBorderColor = ClipPulseColors.Indigo,
    unfocusedBorderColor = ClipPulseColors.Hairline,
    focusedContainerColor = ClipPulseColors.Obsidian,
    unfocusedContainerColor = ClipPulseColors.Obsidian,
    focusedTextColor = ClipPulseColors.TextPrimary,
    unfocusedTextColor = ClipPulseColors.TextPrimary,
    focusedLabelColor = ClipPulseColors.Indigo,
    unfocusedLabelColor = ClipPulseColors.TextSecondary
)
''',
}
