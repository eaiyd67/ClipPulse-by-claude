"""yt-dlp manager, cookies import, 1-arg updater, streaming parsers, 4 detection engines, consensus merger, and ScanRepository."""

FILES = {
    "app/src/main/java/com/clippulse/app/data/scan/StreamingParsers.kt": r'''
package com.clippulse.app.data.scan

import android.util.JsonReader
import android.util.JsonToken
import com.clippulse.app.domain.model.HeatmapPoint
import com.clippulse.app.domain.model.SuperChatEvent
import java.io.BufferedReader
import java.io.File
import java.io.FileInputStream
import java.io.InputStreamReader
import java.io.StringReader
import java.nio.charset.StandardCharsets

data class ParsedInfoJson(
    val id: String,
    val title: String,
    val uploader: String,
    val durationSec: Double,
    val previewStreamUrl: String,
    val streamHeaders: Map<String, String>,
    val thumbnailUrl: String?,
    val heatmap: List<HeatmapPoint>
)

data class TranscriptSegment(
    val startSec: Double,
    val endSec: Double,
    val text: String
)

data class ParsedLiveChat(
    val superChats: List<SuperChatEvent>,
    val messageTimestampsSec: List<Double>
)

object StreamingParsers {

    fun parseInfoJsonFile(file: File, fallbackUrl: String): ParsedInfoJson {
        var id = ""
        var title = "Untitled Video"
        var uploader = "Unknown Creator"
        var durationSec = 0.0
        var directUrl = ""
        var thumbnail: String? = null
        val headers = mutableMapOf<String, String>()
        val heatmap = mutableListOf<HeatmapPoint>()
        var requestedFormatUrl = ""
        var bestCombinedFormatUrl = ""
        var bestCombinedHeight = 0

        JsonReader(InputStreamReader(FileInputStream(file), StandardCharsets.UTF_8)).use { reader ->
            reader.isLenient = true
            if (reader.peek() != JsonToken.BEGIN_OBJECT) {
                return ParsedInfoJson(id, title, uploader, durationSec, fallbackUrl, headers, thumbnail, heatmap)
            }
            reader.beginObject()
            while (reader.hasNext()) {
                when (reader.nextName()) {
                    "id" -> id = readString(reader, id)
                    "title" -> title = readString(reader, title)
                    "uploader", "channel" -> {
                        val candidate = readString(reader, "")
                        if (candidate.isNotBlank() && uploader == "Unknown Creator") {
                            uploader = candidate
                        }
                    }
                    "duration" -> durationSec = readDouble(reader, durationSec)
                    "url" -> directUrl = readString(reader, directUrl)
                    "thumbnail" -> thumbnail = readString(reader, "").ifBlank { thumbnail }
                    "http_headers" -> readHeadersObject(reader, headers)
                    "heatmap" -> readHeatmapArray(reader, heatmap)
                    "requested_formats" -> {
                        val urlFound = readFirstPlayableUrlFromFormats(reader, headers)
                        if (urlFound.isNotBlank()) requestedFormatUrl = urlFound
                    }
                    "formats" -> {
                        val (urlFound, height) = readBestMuxedFormat(reader, headers)
                        if (urlFound.isNotBlank() && height >= bestCombinedHeight) {
                            bestCombinedFormatUrl = urlFound
                            bestCombinedHeight = height
                        }
                    }
                    else -> reader.skipValue()
                }
            }
            reader.endObject()
        }

        val resolvedUrl = when {
            bestCombinedFormatUrl.isNotBlank() -> bestCombinedFormatUrl
            directUrl.isNotBlank() -> directUrl
            requestedFormatUrl.isNotBlank() -> requestedFormatUrl
            else -> fallbackUrl
        }

        return ParsedInfoJson(
            id = id.ifBlank { fallbackUrl.hashCode().toString() },
            title = title,
            uploader = uploader,
            durationSec = durationSec.coerceAtLeast(1.0),
            previewStreamUrl = resolvedUrl,
            streamHeaders = headers,
            thumbnailUrl = thumbnail,
            heatmap = heatmap
        )
    }

    private fun readHeadersObject(reader: JsonReader, target: MutableMap<String, String>) {
        if (reader.peek() != JsonToken.BEGIN_OBJECT) {
            reader.skipValue()
            return
        }
        reader.beginObject()
        while (reader.hasNext()) {
            val k = reader.nextName()
            val v = readString(reader, "")
            if (v.isNotBlank() && !target.containsKey(k)) {
                target[k] = v
            }
        }
        reader.endObject()
    }

    private fun readHeatmapArray(reader: JsonReader, target: MutableList<HeatmapPoint>) {
        if (reader.peek() != JsonToken.BEGIN_ARRAY) {
            reader.skipValue()
            return
        }
        reader.beginArray()
        while (reader.hasNext()) {
            if (reader.peek() != JsonToken.BEGIN_OBJECT) {
                reader.skipValue()
                continue
            }
            var start = 0.0
            var end = 0.0
            var value = 0.0
            reader.beginObject()
            while (reader.hasNext()) {
                when (reader.nextName()) {
                    "start_time" -> start = readDouble(reader, 0.0)
                    "end_time" -> end = readDouble(reader, 0.0)
                    "value" -> value = readDouble(reader, 0.0)
                    else -> reader.skipValue()
                }
            }
            reader.endObject()
            if (end > start) {
                target.add(HeatmapPoint(start, end, value.coerceIn(0.0, 1.0)))
            }
        }
        reader.endArray()
    }

    private fun readFirstPlayableUrlFromFormats(
        reader: JsonReader,
        headers: MutableMap<String, String>
    ): String {
        if (reader.peek() != JsonToken.BEGIN_ARRAY) {
            reader.skipValue()
            return ""
        }
        var found = ""
        reader.beginArray()
        while (reader.hasNext()) {
            if (reader.peek() != JsonToken.BEGIN_OBJECT) {
                reader.skipValue()
                continue
            }
            var url = ""
            var vcodec = ""
            reader.beginObject()
            while (reader.hasNext()) {
                when (reader.nextName()) {
                    "url" -> url = readString(reader, "")
                    "vcodec" -> vcodec = readString(reader, "")
                    "http_headers" -> readHeadersObject(reader, headers)
                    else -> reader.skipValue()
                }
            }
            reader.endObject()
            if (found.isBlank() && url.isNotBlank() && vcodec != "none") {
                found = url
            }
        }
        reader.endArray()
        return found
    }

    private fun readBestMuxedFormat(
        reader: JsonReader,
        headers: MutableMap<String, String>
    ): Pair<String, Int> {
        if (reader.peek() != JsonToken.BEGIN_ARRAY) {
            reader.skipValue()
            return "" to 0
        }
        var bestUrl = ""
        var bestScore = -1
        reader.beginArray()
        while (reader.hasNext()) {
            if (reader.peek() != JsonToken.BEGIN_OBJECT) {
                reader.skipValue()
                continue
            }
            var url = ""
            var ext = ""
            var vcodec = ""
            var acodec = ""
            var protocol = ""
            var height = 0
            reader.beginObject()
            while (reader.hasNext()) {
                when (reader.nextName()) {
                    "url" -> url = readString(reader, "")
                    "ext" -> ext = readString(reader, "")
                    "vcodec" -> vcodec = readString(reader, "")
                    "acodec" -> acodec = readString(reader, "")
                    "protocol" -> protocol = readString(reader, "")
                    "height" -> height = readDouble(reader, 0.0).toInt()
                    "http_headers" -> readHeadersObject(reader, headers)
                    else -> reader.skipValue()
                }
            }
            reader.endObject()

            val hasVideo = vcodec.isNotBlank() && vcodec != "none"
            val hasAudio = acodec.isNotBlank() && acodec != "none"
            val isPlayableProto = protocol == "https" || protocol == "http" || protocol.contains("m3u8")
            if (url.isNotBlank() && hasVideo && hasAudio && isPlayableProto) {
                val mp4Bonus = if (ext == "mp4") 500 else 0
                val cappedHeight = height.coerceAtMost(720)
                val score = mp4Bonus + cappedHeight
                if (score > bestScore) {
                    bestScore = score
                    bestUrl = url
                }
            }
        }
        reader.endArray()
        return bestUrl to bestScore
    }

    fun parseSubtitleFile(file: File): List<TranscriptSegment> {
        val segments = mutableListOf<TranscriptSegment>()
        val timeRegex = Regex(
            "(\\d{1,2}:)?(\\d{2}):(\\d{2})[.,](\\d{3})\\s*-->\\s*(\\d{1,2}:)?(\\d{2}):(\\d{2})[.,](\\d{3})"
        )
        BufferedReader(InputStreamReader(FileInputStream(file), StandardCharsets.UTF_8)).use { br ->
            var currentStart = -1.0
            var currentEnd = -1.0
            val textBuf = StringBuilder()

            fun flush() {
                if (currentStart >= 0.0 && currentEnd > currentStart) {
                    val cleaned = textBuf.toString()
                        .replace(Regex("<[^>]+>"), " ")
                        .replace(Regex("\\s+"), " ")
                        .trim()
                    if (cleaned.isNotEmpty()) {
                        val last = segments.lastOrNull()
                        if (last == null || last.text != cleaned) {
                            segments.add(TranscriptSegment(currentStart, currentEnd, cleaned))
                        }
                    }
                }
                currentStart = -1.0
                currentEnd = -1.0
                textBuf.setLength(0)
            }

            while (true) {
                val line = br.readLine() ?: break
                val trimmed = line.trim()
                if (trimmed.isEmpty()) {
                    flush()
                    continue
                }
                val match = timeRegex.find(trimmed)
                if (match != null) {
                    flush()
                    currentStart = parseClockParts(
                        match.groupValues[1],
                        match.groupValues[2],
                        match.groupValues[3],
                        match.groupValues[4]
                    )
                    currentEnd = parseClockParts(
                        match.groupValues[5],
                        match.groupValues[6],
                        match.groupValues[7],
                        match.groupValues[8]
                    )
                } else if (currentStart >= 0.0 && !trimmed.startsWith("WEBVTT") && !trimmed.startsWith("NOTE")) {
                    if (textBuf.isNotEmpty()) textBuf.append(' ')
                    textBuf.append(trimmed)
                }
            }
            flush()
        }
        return segments
    }

    private fun parseClockParts(hRaw: String, mRaw: String, sRaw: String, msRaw: String): Double {
        val h = hRaw.removeSuffix(":").toDoubleOrNull() ?: 0.0
        val m = mRaw.toDoubleOrNull() ?: 0.0
        val s = sRaw.toDoubleOrNull() ?: 0.0
        val ms = msRaw.toDoubleOrNull() ?: 0.0
        return h * 3600.0 + m * 60.0 + s + (ms / 1000.0)
    }

    fun parseLiveChatFile(file: File): ParsedLiveChat {
        val superChats = mutableListOf<SuperChatEvent>()
        val timestamps = mutableListOf<Double>()

        BufferedReader(InputStreamReader(FileInputStream(file), StandardCharsets.UTF_8)).use { br ->
            while (true) {
                val line = br.readLine() ?: break
                val trimmed = line.trim()
                if (trimmed.isEmpty() || !trimmed.startsWith("{")) continue
                runCatching {
                    JsonReader(StringReader(trimmed)).use { reader ->
                        reader.isLenient = true
                        parseLiveChatLine(reader, superChats, timestamps)
                    }
                }
            }
        }
        return ParsedLiveChat(superChats = superChats, messageTimestampsSec = timestamps)
    }

    private fun parseLiveChatLine(
        reader: JsonReader,
        superChats: MutableList<SuperChatEvent>,
        timestamps: MutableList<Double>
    ) {
        var offsetMs: Long? = null
        var pendingPaidEvent: SuperChatEvent? = null
        var sawChatMessage = false

        reader.beginObject()
        while (reader.hasNext()) {
            when (reader.nextName()) {
                "videoOffsetTimeMsec" -> offsetMs = readLong(reader)
                "replayChatItemAction" -> {
                    if (reader.peek() == JsonToken.BEGIN_OBJECT) {
                        reader.beginObject()
                        while (reader.hasNext()) {
                            when (reader.nextName()) {
                                "videoOffsetTimeMsec" -> offsetMs = readLong(reader)
                                "actions" -> {
                                    if (reader.peek() == JsonToken.BEGIN_ARRAY) {
                                        reader.beginArray()
                                        while (reader.hasNext()) {
                                            if (reader.peek() == JsonToken.BEGIN_OBJECT) {
                                                val parsed = parseChatAction(reader)
                                                if (parsed.first) sawChatMessage = true
                                                if (parsed.second != null) pendingPaidEvent = parsed.second
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
                    } else {
                        reader.skipValue()
                    }
                }
                else -> reader.skipValue()
            }
        }
        reader.endObject()

        val sec = (offsetMs ?: 0L).toDouble() / 1000.0
        if (sec >= 0.0 && (sawChatMessage || pendingPaidEvent != null)) {
            timestamps.add(sec)
        }
        if (pendingPaidEvent != null && sec >= 0.0) {
            superChats.add(pendingPaidEvent!!.copy(timestampSec = sec))
        }
    }

    private fun parseChatAction(reader: JsonReader): Pair<Boolean, SuperChatEvent?> {
        var sawMsg = false
        var superChat: SuperChatEvent? = null
        reader.beginObject()
        while (reader.hasNext()) {
            when (reader.nextName()) {
                "addChatItemAction" -> {
                    if (reader.peek() == JsonToken.BEGIN_OBJECT) {
                        reader.beginObject()
                        while (reader.hasNext()) {
                            if (reader.nextName() == "item" && reader.peek() == JsonToken.BEGIN_OBJECT) {
                                reader.beginObject()
                                while (reader.hasNext()) {
                                    when (reader.nextName()) {
                                        "liveChatTextMessageRenderer" -> {
                                            sawMsg = true
                                            reader.skipValue()
                                        }
                                        "liveChatPaidMessageRenderer" -> {
                                            sawMsg = true
                                            superChat = parsePaidRenderer(reader)
                                        }
                                        "liveChatPaidStickerRenderer" -> {
                                            sawMsg = true
                                            superChat = parsePaidRenderer(reader)
                                        }
                                        else -> reader.skipValue()
                                    }
                                }
                                reader.endObject()
                            } else {
                                reader.skipValue()
                            }
                        }
                        reader.endObject()
                    } else {
                        reader.skipValue()
                    }
                }
                else -> reader.skipValue()
            }
        }
        reader.endObject()
        return sawMsg to superChat
    }

    private fun parsePaidRenderer(reader: JsonReader): SuperChatEvent {
        var author = "Viewer"
        var amount = "Super Chat"
        var message = ""
        var bgColor = 0xFFF59E0B
        reader.beginObject()
        while (reader.hasNext()) {
            when (reader.nextName()) {
                "authorName" -> author = readRunsOrSimpleText(reader).ifBlank { author }
                "purchaseAmountText" -> amount = readRunsOrSimpleText(reader).ifBlank { amount }
                "message" -> message = readRunsOrSimpleText(reader)
                "bodyBackgroundColor", "headerBackgroundColor" -> {
                    val rawColor = readLong(reader)
                    if (rawColor != null && rawColor > 0L) {
                        bgColor = (rawColor and 0xFFFFFFFFL)
                    }
                }
                else -> reader.skipValue()
            }
        }
        reader.endObject()
        return SuperChatEvent(
            timestampSec = 0.0,
            author = author,
            amountText = amount,
            message = message.ifBlank { "Sent a Super Chat" },
            tierColorHex = bgColor
        )
    }

    private fun readRunsOrSimpleText(reader: JsonReader): String {
        if (reader.peek() != JsonToken.BEGIN_OBJECT) {
            reader.skipValue()
            return ""
        }
        val sb = StringBuilder()
        reader.beginObject()
        while (reader.hasNext()) {
            when (reader.nextName()) {
                "simpleText" -> sb.append(readString(reader, ""))
                "runs" -> {
                    if (reader.peek() == JsonToken.BEGIN_ARRAY) {
                        reader.beginArray()
                        while (reader.hasNext()) {
                            if (reader.peek() == JsonToken.BEGIN_OBJECT) {
                                reader.beginObject()
                                while (reader.hasNext()) {
                                    if (reader.nextName() == "text") {
                                        sb.append(readString(reader, ""))
                                    } else {
                                        reader.skipValue()
                                    }
                                }
                                reader.endObject()
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
        return sb.toString().trim()
    }

    private fun readString(reader: JsonReader, fallback: String): String {
        return when (reader.peek()) {
            JsonToken.STRING -> reader.nextString()
            JsonToken.NUMBER -> reader.nextString()
            else -> {
                reader.skipValue()
                fallback
            }
        }
    }

    private fun readDouble(reader: JsonReader, fallback: Double): Double {
        return when (reader.peek()) {
            JsonToken.NUMBER -> reader.nextDouble()
            JsonToken.STRING -> reader.nextString().toDoubleOrNull() ?: fallback
            else -> {
                reader.skipValue()
                fallback
            }
        }
    }

    private fun readLong(reader: JsonReader): Long? {
        return when (reader.peek()) {
            JsonToken.NUMBER -> reader.nextLong()
            JsonToken.STRING -> reader.nextString().toLongOrNull()
            else -> {
                reader.skipValue()
                null
            }
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/data/scan/YtDlpManager.kt": r'''
package com.clippulse.app.data.scan

import android.content.Context
import android.media.MediaMetadataRetriever
import android.net.Uri
import android.provider.OpenableColumns
import com.clippulse.app.data.PrefsRepo
import com.clippulse.app.domain.model.AppResult
import com.clippulse.app.domain.model.VideoMetadata
import com.clippulse.app.util.ErrorSanitizer
import com.yausername.aria2c.Aria2c
import com.yausername.ffmpeg.FFmpeg
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.util.Locale
import java.util.UUID

data class ExtractedScanBundle(
    val metadata: VideoMetadata,
    val transcriptSegments: List<TranscriptSegment>,
    val chatTimestampsSec: List<Double>,
    val clientUsed: String
)

class YtDlpManager(
    private val appContext: Context,
    private val prefsRepo: PrefsRepo
) {

    @Volatile
    private var initialized = false
    private val initLock = Any()

    fun ensureInitialized(): AppResult<Unit> {
        if (initialized) return AppResult.Success(Unit)
        synchronized(initLock) {
            if (initialized) return AppResult.Success(Unit)
            return try {
                YoutubeDL.getInstance().init(appContext)
                FFmpeg.getInstance().init(appContext)
                Aria2c.getInstance().init(appContext)
                initialized = true
                AppResult.Success(Unit)
            } catch (e: Exception) {
                AppResult.Error(ErrorSanitizer.sanitize(e.message, "Failed to initialize yt-dlp engine."), cause = e)
            }
        }
    }

    suspend fun updateEngine(): AppResult<String> = withContext(Dispatchers.IO) {
        val initRes = ensureInitialized()
        if (initRes is AppResult.Error) return@withContext initRes
        try {
            val status = YoutubeDL.getInstance().updateYoutubeDL(appContext)
            prefsRepo.setLastEngineUpdateMs(System.currentTimeMillis())
            val msg = when (status) {
                YoutubeDL.UpdateStatus.DONE -> "yt-dlp updated to latest version."
                YoutubeDL.UpdateStatus.ALREADY_UP_TO_DATE -> "yt-dlp is already up to date."
                null -> "yt-dlp update check completed."
            }
            AppResult.Success(msg)
        } catch (e: Exception) {
            AppResult.Error(ErrorSanitizer.sanitize(e.message, "Engine update failed."), cause = e)
        }
    }

    suspend fun importCookiesFromUri(uri: Uri): AppResult<String> = withContext(Dispatchers.IO) {
        try {
            val target = File(appContext.filesDir, "cookies.txt")
            appContext.contentResolver.openInputStream(uri)?.use { input ->
                FileOutputStream(target).use { output ->
                    input.copyTo(output)
                }
            } ?: return@withContext AppResult.Error("Unable to open selected cookies.txt file.")

            if (target.length() <= 0L) {
                target.delete()
                return@withContext AppResult.Error("Selected cookies.txt file is empty.")
            }
            prefsRepo.setCookiesPath(target.absolutePath)
            AppResult.Success("Cookies imported (${target.length()} bytes)")
        } catch (e: Exception) {
            AppResult.Error(ErrorSanitizer.sanitize(e.message, "Failed to import cookies.txt"), cause = e)
        }
    }

    fun clearCookies() {
        val existing = prefsRepo.cookiesPath.value
        if (existing.isNotBlank()) {
            runCatching { File(existing).delete() }
        }
        prefsRepo.setCookiesPath("")
    }

    fun activeCookiesFile(): File? {
        val path = prefsRepo.cookiesPath.value
        if (path.isBlank()) return null
        val f = File(path)
        return if (f.exists() && f.length() > 0L) f else null
    }

    fun cancelProcess(processId: String) {
        runCatching {
            YoutubeDL.getInstance().destroyProcessById(processId)
        }
    }

    suspend fun inspectLocalVideo(uri: Uri): AppResult<ExtractedScanBundle> = withContext(Dispatchers.IO) {
        val retriever = MediaMetadataRetriever()
        try {
            retriever.setDataSource(appContext, uri)
            val durationMs = retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)?.toLongOrNull() ?: 0L
            val title = queryDisplayName(uri) ?: "Local Video"
            val durationSec = (durationMs.toDouble() / 1000.0).coerceAtLeast(1.0)
            val metadata = VideoMetadata(
                id = "local_${uri.toString().hashCode()}",
                sourceUrl = uri.toString(),
                title = title,
                uploader = "Local Storage",
                durationSec = durationSec,
                previewStreamUrl = uri.toString(),
                isLocalFile = true,
                localUri = uri.toString()
            )
            AppResult.Success(
                ExtractedScanBundle(
                    metadata = metadata,
                    transcriptSegments = emptyList(),
                    chatTimestampsSec = emptyList(),
                    clientUsed = "local"
                )
            )
        } catch (e: Exception) {
            AppResult.Error(ErrorSanitizer.sanitize(e.message, "Could not inspect local video file."), cause = e)
        } finally {
            runCatching { retriever.release() }
        }
    }

    suspend fun extractRemoteScanBundle(
        url: String,
        processId: String,
        onStage: (String) -> Unit
    ): AppResult<ExtractedScanBundle> = withContext(Dispatchers.IO) {
        val initRes = ensureInitialized()
        if (initRes is AppResult.Error) return@withContext initRes

        val isYouTube = url.contains("youtube.com", true) || url.contains("youtu.be", true)
        val clientRotation: List<Pair<String, String?>> = if (isYouTube) {
            listOf(
                "tv_embedded,mweb" to "youtube:player_client=tv_embedded,mweb",
                "ios,web" to "youtube:player_client=ios,web",
                "default" to null
            )
        } else {
            listOf("default" to null)
        }

        val cookiesFile = activeCookiesFile()
        var lastError = "Failed to extract video metadata."

        for ((clientLabel, extractorArgs) in clientRotation) {
            onStage("Extracting metadata ($clientLabel)...")
            val workDir = File(appContext.cacheDir, "scan_${UUID.randomUUID().toString().take(8)}")
            workDir.mkdirs()

            try {
                val request = YoutubeDLRequest(url).apply {
                    addOption("--skip-download")
                    addOption("--write-info-json")
                    addOption("--no-playlist")
                    addOption("--no-warnings")
                    addOption("--socket-timeout", "20")
                    addOption("--retries", "2")
                    addOption("-f", "best[height<=720][ext=mp4]/best[height<=720]/best")
                    addOption("-o", File(workDir, "video.%(ext)s").absolutePath)
                    if (isYouTube) {
                        addOption("--write-auto-subs")
                        addOption("--write-subs")
                        addOption("--sub-langs", "en,hi,bn,live_chat")
                        addOption("--sub-format", "vtt/best")
                    }
                    if (extractorArgs != null) {
                        addOption("--extractor-args", extractorArgs)
                    }
                    if (cookiesFile != null) {
                        addOption("--cookies", cookiesFile.absolutePath)
                    }
                }

                YoutubeDL.getInstance().execute(request, processId) { _, _, _ -> }

                val infoFile = workDir.listFiles()?.firstOrNull { it.name.endsWith(".info.json") }
                if (infoFile != null && infoFile.exists()) {
                    onStage("Streaming metadata, subtitles & chat...")
                    val parsedInfo = StreamingParsers.parseInfoJsonFile(infoFile, url)

                    val subFiles = workDir.listFiles()
                        ?.filter { it.name.endsWith(".vtt") || it.name.endsWith(".srt") }
                        .orEmpty()
                    val transcriptSegments = mutableListOf<TranscriptSegment>()
                    for (sf in subFiles.take(2)) {
                        runCatching {
                            transcriptSegments.addAll(StreamingParsers.parseSubtitleFile(sf))
                        }
                    }

                    val chatFile = workDir.listFiles()?.firstOrNull { it.name.endsWith(".live_chat.json") }
                    val parsedChat = if (chatFile != null && chatFile.exists()) {
                        runCatching { StreamingParsers.parseLiveChatFile(chatFile) }
                            .getOrDefault(ParsedLiveChat(emptyList(), emptyList()))
                    } else {
                        ParsedLiveChat(emptyList(), emptyList())
                    }

                    val transcriptSnippet = transcriptSegments
                        .take(80)
                        .joinToString("\n") { seg ->
                            String.format(Locale.US, "[%.1f-%.1f] %s", seg.startSec, seg.endSec, seg.text)
                        }

                    val metadata = VideoMetadata(
                        id = parsedInfo.id,
                        sourceUrl = url,
                        title = parsedInfo.title,
                        uploader = parsedInfo.uploader,
                        durationSec = parsedInfo.durationSec,
                        previewStreamUrl = parsedInfo.previewStreamUrl,
                        streamHeaders = parsedInfo.streamHeaders,
                        isLocalFile = false,
                        localUri = null,
                        thumbnailUrl = parsedInfo.thumbnailUrl,
                        heatmap = parsedInfo.heatmap,
                        superChats = parsedChat.superChats,
                        transcriptSnippet = transcriptSnippet
                    )

                    return@withContext AppResult.Success(
                        ExtractedScanBundle(
                            metadata = metadata,
                            transcriptSegments = transcriptSegments,
                            chatTimestampsSec = parsedChat.messageTimestampsSec,
                            clientUsed = clientLabel
                        )
                    )
                }
            } catch (e: Exception) {
                lastError = ErrorSanitizer.sanitize(e.message, "Extraction error with $clientLabel.")
            } finally {
                runCatching { workDir.deleteRecursively() }
            }
        }

        AppResult.Error(lastError)
    }

    suspend fun downloadSection(
        sourceUrl: String,
        startSec: Double,
        endSec: Double,
        outputTemplatePath: String,
        useAria2cFallback: Boolean,
        processId: String,
        onProgress: (Float, String) -> Unit
    ): AppResult<File> = withContext(Dispatchers.IO) {
        val initRes = ensureInitialized()
        if (initRes is AppResult.Error) return@withContext initRes

        val parentDir = File(outputTemplatePath).parentFile ?: appContext.cacheDir
        val isYouTube = sourceUrl.contains("youtube.com", true) || sourceUrl.contains("youtu.be", true)
        val clients: List<String?> = if (isYouTube) {
            listOf("youtube:player_client=tv_embedded,mweb", "youtube:player_client=ios,web", null)
        } else {
            listOf(null)
        }
        val cookiesFile = activeCookiesFile()
        val sectionSpec = String.format(Locale.US, "*%.2f-%.2f", startSec.coerceAtLeast(0.0), endSec)

        var lastError = "Failed to download clip section."
        for (clientArg in clients) {
            try {
                val request = YoutubeDLRequest(sourceUrl).apply {
                    addOption("--no-playlist")
                    addOption("--no-warnings")
                    addOption("--download-sections", sectionSpec)
                    addOption("--force-keyframes-at-cuts")
                    addOption("-f", "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080][ext=mp4]/best")
                    addOption("--merge-output-format", "mp4")
                    addOption("-o", outputTemplatePath)
                    if (clientArg != null) {
                        addOption("--extractor-args", clientArg)
                    }
                    if (cookiesFile != null) {
                        addOption("--cookies", cookiesFile.absolutePath)
                    }
                    if (useAria2cFallback) {
                        addOption("--downloader", "aria2c")
                        addOption("--downloader-args", "aria2c:-x 4 -s 4 -k 1M")
                    }
                }

                YoutubeDL.getInstance().execute(request, processId) { progress, _, line ->
                    val normalized = (progress / 100f).coerceIn(0f, 1f)
                    onProgress(normalized, line)
                }

                val produced = parentDir.listFiles()
                    ?.filter { it.isFile && it.length() > 1024L && (it.name.endsWith(".mp4") || it.name.endsWith(".mkv") || it.name.endsWith(".webm")) }
                    ?.maxByOrNull { it.lastModified() }
                if (produced != null) {
                    return@withContext AppResult.Success(produced)
                }
            } catch (e: Exception) {
                lastError = ErrorSanitizer.sanitize(e.message, "Section download failed.")
            }
        }
        AppResult.Error(lastError)
    }

    private fun queryDisplayName(uri: Uri): String? {
        return runCatching {
            appContext.contentResolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME), null, null, null)?.use { cursor ->
                if (cursor.moveToFirst()) cursor.getString(0) else null
            }
        }.getOrNull()
    }
}
''',

    "app/src/main/java/com/clippulse/app/domain/engine/DetectionEngines.kt": r'''
package com.clippulse.app.domain.engine

import com.clippulse.app.data.scan.TranscriptSegment
import com.clippulse.app.domain.model.ClipCandidate
import com.clippulse.app.domain.model.HeatmapPoint
import com.clippulse.app.domain.model.Signal
import com.clippulse.app.domain.model.SignalType
import com.clippulse.app.domain.model.SuperChatEvent
import com.clippulse.app.domain.model.VideoMetadata
import java.util.Locale
import java.util.UUID
import kotlin.math.abs
import kotlin.math.sqrt

interface SignalEngine {
    fun detect(): List<Signal>
}

class HeatmapEngine(
    private val heatmap: List<HeatmapPoint>,
    private val durationSec: Double
) : SignalEngine {

    override fun detect(): List<Signal> {
        if (heatmap.size < 3) return emptyList()
        val avg = heatmap.map { it.value }.average()
        val variance = heatmap.map { (it.value - avg) * (it.value - avg) }.average()
        val std = sqrt(variance).coerceAtLeast(0.05)
        val threshold = (avg + 0.65 * std).coerceIn(0.42, 0.85)

        val peaks = mutableListOf<Int>()
        for (i in 1 until heatmap.lastIndex) {
            val v = heatmap[i].value
            if (v >= threshold && v >= heatmap[i - 1].value && v >= heatmap[i + 1].value) {
                peaks.add(i)
            }
        }
        if (peaks.isEmpty()) {
            val bestIdx = heatmap.indices.maxByOrNull { heatmap[it].value } ?: return emptyList()
            if (heatmap[bestIdx].value >= 0.35) peaks.add(bestIdx)
        }

        val signals = mutableListOf<Signal>()
        for (peakIdx in peaks.sortedByDescending { heatmap[it].value }.take(8)) {
            var left = peakIdx
            while (left > 0 && heatmap[left - 1].value <= heatmap[left].value && (heatmap[peakIdx].endSec - heatmap[left - 1].startSec) < 35.0) {
                left--
            }
            var right = peakIdx
            while (right < heatmap.lastIndex && heatmap[right + 1].value <= heatmap[right].value && (heatmap[right + 1].endSec - heatmap[left].startSec) < 55.0) {
                right++
            }
            val start = heatmap[left].startSec.coerceIn(0.0, durationSec)
            val end = heatmap[right].endSec.coerceIn(start + 12.0, durationSec.coerceAtLeast(start + 12.0))
            val score = heatmap[peakIdx].value.coerceIn(0.2, 1.0)
            signals.add(
                Signal(
                    start = start,
                    end = end,
                    score = score,
                    type = SignalType.HEATMAP,
                    label = "Most Replayed Peak",
                    meta = String.format(Locale.US, "Replay intensity %.0f%% (valley-to-valley)", score * 100.0)
                )
            )
        }
        return signals
    }
}

class TranscriptExcitementEngine(
    private val segments: List<TranscriptSegment>,
    private val durationSec: Double
) : SignalEngine {

    private val enKeywords = setOf(
        "insane", "crazy", "unbelievable", "omg", "oh my god", "no way", "wait", "bro",
        "clutch", "massive", "secret", "shocking", "exposed", "finally", "impossible",
        "wtf", "literally", "watch this", "plot twist", "legendary", "hilarious", "boom"
    )
    private val hiKeywords = setOf(
        "bhai", "arey", "kya baat", "bawal", "gazab", "pagal", "sach mein", "maza aa gaya",
        "khatarnak", "dhamaka", "ruk jao", "dekh lo", "paisa vasool", "arre yaar",
        "भाई", "गजब", "कमाल", "बवाल", "अरे", "पागल", "खतरनाक", "धमाका", "सच में"
    )
    private val bnKeywords = setOf(
        "bhai", "osthir", "darun", "ki obostha", "matha noshto", "seraa", "sera", "bapre",
        "shotti", "dekho", "khela hobe", "joss", "fatafati",
        "অস্থির", "দারুণ", "সেরা", "মাথা নষ্ট", "ফাটাফাটি", "সত্যি", "খেলা হবে", "বাপরে", "জোস"
    )

    override fun detect(): List<Signal> {
        if (segments.isEmpty()) return emptyList()
        val windowSec = 24.0
        val stepSec = 12.0
        val signals = mutableListOf<Signal>()

        var cursor = 0.0
        while (cursor < durationSec) {
            val winEnd = (cursor + windowSec).coerceAtMost(durationSec)
            val slice = segments.filter { it.endSec >= cursor && it.startSec <= winEnd }
            if (slice.isNotEmpty()) {
                val combined = slice.joinToString(" ") { it.text }
                val lower = combined.lowercase(Locale.US)
                var hits = 0
                val matchedWords = mutableListOf<String>()
                for (kw in enKeywords) {
                    if (lower.contains(kw)) {
                        hits += 2
                        if (matchedWords.size < 3) matchedWords.add(kw)
                    }
                }
                for (kw in hiKeywords) {
                    if (lower.contains(kw)) {
                        hits += 2
                        if (matchedWords.size < 3) matchedWords.add(kw)
                    }
                }
                for (kw in bnKeywords) {
                    if (lower.contains(kw)) {
                        hits += 2
                        if (matchedWords.size < 3) matchedWords.add(kw)
                    }
                }
                val exclamations = combined.count { it == '!' || it == '?' }
                val wordCount = combined.split(Regex("\\s+")).count { it.isNotBlank() }
                val paceBonus = if (wordCount >= 48) 2 else if (wordCount >= 32) 1 else 0
                val rawPoints = hits + exclamations + paceBonus
                if (rawPoints >= 3) {
                    val normScore = (rawPoints.toDouble() / 10.0).coerceIn(0.35, 0.96)
                    val cue = matchedWords.joinToString(", ").ifBlank { "High vocal pace" }
                    signals.add(
                        Signal(
                            start = cursor,
                            end = winEnd,
                            score = normScore,
                            type = SignalType.AUDIO_EXCITEMENT,
                            label = "High-Energy Speech",
                            meta = "Transcript cues: $cue"
                        )
                    )
                }
            }
            cursor += stepSec
        }

        return signals.sortedByDescending { it.score }.take(10)
    }
}

class SuperChatEngine(
    private val superChats: List<SuperChatEvent>,
    private val durationSec: Double
) : SignalEngine {

    override fun detect(): List<Signal> {
        if (superChats.isEmpty()) return emptyList()
        return superChats.map { sc ->
            val start = (sc.timestampSec - 5.0).coerceAtLeast(0.0)
            val end = (sc.timestampSec + 25.0).coerceAtMost(durationSec.coerceAtLeast(start + 10.0))
            val numericAmount = Regex("[0-9]+(\\.[0-9]+)?")
                .find(sc.amountText.replace(",", ""))
                ?.value
                ?.toDoubleOrNull() ?: 5.0
            val score = (0.68 + (numericAmount / 100.0).coerceAtMost(0.30)).coerceIn(0.68, 0.98)
            Signal(
                start = start,
                end = end,
                score = score,
                type = SignalType.SUPER_CHAT,
                label = "Super Chat • ${sc.amountText}",
                meta = "${sc.author}: ${sc.message.take(90)}"
            )
        }.sortedByDescending { it.score }.take(12)
    }
}

class ChatVelocityEngine(
    private val timestampsSec: List<Double>,
    private val durationSec: Double
) : SignalEngine {

    override fun detect(): List<Signal> {
        if (timestampsSec.size < 15) return emptyList()
        val bucketSec = 10.0
        val bucketCount = ((durationSec / bucketSec).toInt() + 1).coerceAtLeast(1)
        val counts = IntArray(bucketCount)
        for (ts in timestampsSec) {
            val idx = (ts / bucketSec).toInt().coerceIn(0, bucketCount - 1)
            counts[idx]++
        }
        val mean = counts.average()
        val std = sqrt(counts.map { (it - mean) * (it - mean) }.average()).coerceAtLeast(1.0)

        val signals = mutableListOf<Signal>()
        for (i in counts.indices) {
            val z = (counts[i].toDouble() - mean) / std
            if (z >= 1.6 && counts[i] >= 4) {
                val center = i * bucketSec
                val start = (center - 6.0).coerceAtLeast(0.0)
                val end = (center + 24.0).coerceAtMost(durationSec.coerceAtLeast(start + 12.0))
                val score = (0.50 + (z / 6.0)).coerceIn(0.55, 0.97)
                signals.add(
                    Signal(
                        start = start,
                        end = end,
                        score = score,
                        type = SignalType.CHAT_VELOCITY,
                        label = "Chat Hype Spike",
                        meta = String.format(Locale.US, "%d msgs/10s (%.1fx above avg)", counts[i], (counts[i] / mean.coerceAtLeast(0.5)))
                    )
                )
            }
        }
        return signals.sortedByDescending { it.score }.take(10)
    }
}

object ConsensusMerger {

    fun merge(
        signals: List<Signal>,
        metadata: VideoMetadata,
        prePadSec: Double = 2.0,
        postPadSec: Double = 3.0,
        minDurationSec: Double = 12.0,
        maxDurationSec: Double = 60.0
    ): List<ClipCandidate> {
        val dur = metadata.durationSec.coerceAtLeast(1.0)
        if (signals.isEmpty()) {
            return buildFallbackCandidates(metadata)
        }

        val sorted = signals.sortedBy { it.start }
        val clusters = mutableListOf<MutableList<Signal>>()

        for (sig in sorted) {
            val lastCluster = clusters.lastOrNull()
            if (lastCluster == null) {
                clusters.add(mutableListOf(sig))
            } else {
                val clusterEnd = lastCluster.maxOf { it.end }
                val clusterStart = lastCluster.minOf { it.start }
                val overlapsOrClose = sig.start <= clusterEnd + 4.0 && (sig.end - clusterStart) <= maxDurationSec + 10.0
                if (overlapsOrClose) {
                    lastCluster.add(sig)
                } else {
                    clusters.add(mutableListOf(sig))
                }
            }
        }

        val candidates = clusters.mapNotNull { group ->
            val rawStart = group.minOf { it.start }
            val rawEnd = group.maxOf { it.end }
            var start = (rawStart - prePadSec).coerceAtLeast(0.0)
            var end = (rawEnd + postPadSec).coerceAtMost(dur)

            val span = end - start
            if (span < minDurationSec) {
                val needed = minDurationSec - span
                start = (start - needed * 0.4).coerceAtLeast(0.0)
                end = (start + minDurationSec).coerceAtMost(dur)
            } else if (span > maxDurationSec) {
                val bestSignal = group.maxByOrNull { it.score } ?: group.first()
                val anchor = (bestSignal.start + bestSignal.end) / 2.0
                start = (anchor - maxDurationSec * 0.45).coerceIn(0.0, (dur - maxDurationSec).coerceAtLeast(0.0))
                end = (start + maxDurationSec).coerceAtMost(dur)
            }

            if (end - start < 4.0) return@mapNotNull null

            val distinctTypes = group.map { it.type }.distinct()
            val primary = group.maxByOrNull { it.score } ?: group.first()
            val maxScore = group.maxOf { it.score }
            val consensusBonus = ((distinctTypes.size - 1) * 0.08).coerceAtMost(0.20)
            val finalScore = (maxScore + consensusBonus).coerceIn(0.1, 0.99)

            val matchedSuperChat = metadata.superChats.firstOrNull { sc ->
                sc.timestampSec >= start - 2.0 && sc.timestampSec <= end + 2.0
            }

            val title = primary.label.ifBlank { "${primary.type.label} Highlight" }
            val reason = group
                .distinctBy { it.type }
                .joinToString(" • ") { it.meta.ifBlank { it.type.label } }

            ClipCandidate(
                id = UUID.randomUUID().toString(),
                startSec = start,
                endSec = end,
                score = finalScore,
                primarySignal = primary.type,
                signals = distinctTypes,
                title = title,
                reason = reason,
                superChat = matchedSuperChat
            )
        }

        val ranked = candidates.sortedByDescending { it.score }
        val deduped = mutableListOf<ClipCandidate>()
        for (cand in ranked) {
            val tooClose = deduped.any { existing ->
                abs(existing.startSec - cand.startSec) < 6.0 && abs(existing.endSec - cand.endSec) < 6.0
            }
            if (!tooClose) deduped.add(cand)
        }

        return deduped.take(15).ifEmpty { buildFallbackCandidates(metadata) }
    }

    private fun buildFallbackCandidates(metadata: VideoMetadata): List<ClipCandidate> {
        val dur = metadata.durationSec.coerceAtLeast(5.0)
        val clipLen = minOf(30.0, dur)
        val count = when {
            dur <= 45.0 -> 1
            dur <= 180.0 -> 3
            else -> 4
        }
        val step = if (count == 1) 0.0 else (dur - clipLen) / (count - 1).toDouble()
        return List(count) { idx ->
            val start = (idx * step).coerceIn(0.0, (dur - clipLen).coerceAtLeast(0.0))
            val end = (start + clipLen).coerceAtMost(dur)
            ClipCandidate(
                id = UUID.randomUUID().toString(),
                startSec = start,
                endSec = end,
                score = 0.60 - (idx * 0.04),
                primarySignal = SignalType.AUDIO_EXCITEMENT,
                signals = listOf(SignalType.AUDIO_EXCITEMENT),
                title = "Highlight Segment #${idx + 1}",
                reason = "Auto-segmented window ready for drag-to-trim"
            )
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/data/scan/ScanRepository.kt": r'''
package com.clippulse.app.data.scan

import android.content.Context
import android.net.Uri
import com.clippulse.app.data.PrefsRepo
import com.clippulse.app.data.ai.AiClient
import com.clippulse.app.domain.engine.ChatVelocityEngine
import com.clippulse.app.domain.engine.ConsensusMerger
import com.clippulse.app.domain.engine.HeatmapEngine
import com.clippulse.app.domain.engine.SuperChatEngine
import com.clippulse.app.domain.engine.TranscriptExcitementEngine
import com.clippulse.app.domain.model.AppResult
import com.clippulse.app.domain.model.ClipCandidate
import com.clippulse.app.domain.model.ScanHistoryItem
import com.clippulse.app.domain.model.Signal
import com.clippulse.app.domain.model.VideoMetadata
import com.clippulse.app.domain.model.ViralCopyPack
import com.clippulse.app.util.UrlNormalizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.UUID

data class ScanOutcome(
    val metadata: VideoMetadata,
    val clips: List<ClipCandidate>,
    val clientUsed: String,
    val aiWarning: String? = null
)

class ScanRepository(
    private val context: Context,
    private val ytDlpManager: YtDlpManager,
    private val aiClient: AiClient,
    private val prefsRepo: PrefsRepo
) {

    suspend fun scanUrl(
        rawInput: String,
        processId: String,
        onStage: (String) -> Unit
    ): AppResult<ScanOutcome> = withContext(Dispatchers.IO) {
        val normalized = UrlNormalizer.normalizeVideoUrl(rawInput)
        if (normalized.isBlank()) {
            return@withContext AppResult.Error("Paste a YouTube, livestream VOD, Facebook URL, or pick a local video.")
        }

        val bundleResult = if (UrlNormalizer.isLocalContentUri(normalized)) {
            onStage("Inspecting local video...")
            ytDlpManager.inspectLocalVideo(Uri.parse(normalized))
        } else {
            ytDlpManager.extractRemoteScanBundle(normalized, processId, onStage)
        }

        val bundle = when (bundleResult) {
            is AppResult.Success -> bundleResult.data
            is AppResult.Error -> return@withContext bundleResult
        }

        onStage("Running detection engines...")
        val allSignals = mutableListOf<Signal>()
        allSignals.addAll(HeatmapEngine(bundle.metadata.heatmap, bundle.metadata.durationSec).detect())
        allSignals.addAll(TranscriptExcitementEngine(bundle.transcriptSegments, bundle.metadata.durationSec).detect())
        allSignals.addAll(SuperChatEngine(bundle.metadata.superChats, bundle.metadata.durationSec).detect())
        allSignals.addAll(ChatVelocityEngine(bundle.chatTimestampsSec, bundle.metadata.durationSec).detect())

        var aiWarning: String? = null
        val aiCfg = prefsRepo.aiConfig.value
        if (!aiCfg.offlineMode && aiCfg.isConnected && bundle.metadata.transcriptSnippet.isNotBlank()) {
            onStage("Scoring viral hooks with AI...")
            when (val aiRes = aiClient.detectAiPicks(bundle.metadata, bundle.metadata.transcriptSnippet)) {
                is AppResult.Success -> allSignals.addAll(aiRes.data)
                is AppResult.Error -> aiWarning = aiRes.message
            }
        }

        onStage("Merging consensus highlights...")
        val clips = ConsensusMerger.merge(
            signals = allSignals,
            metadata = bundle.metadata
        )

        prefsRepo.addScanHistory(
            ScanHistoryItem(
                id = UUID.randomUUID().toString(),
                sourceUrl = bundle.metadata.sourceUrl,
                title = bundle.metadata.title,
                uploader = bundle.metadata.uploader,
                durationSec = bundle.metadata.durationSec,
                clipCount = clips.size,
                scannedAtMs = System.currentTimeMillis(),
                isLocalFile = bundle.metadata.isLocalFile
            )
        )

        AppResult.Success(
            ScanOutcome(
                metadata = bundle.metadata,
                clips = clips,
                clientUsed = bundle.clientUsed,
                aiWarning = aiWarning
            )
        )
    }

    suspend fun generateViralCopyPack(
        clip: ClipCandidate,
        metadata: VideoMetadata
    ): AppResult<ViralCopyPack> = aiClient.generateViralCopyPack(clip, metadata)

    suspend fun importCookies(uri: Uri): AppResult<String> = ytDlpManager.importCookiesFromUri(uri)

    fun clearCookies() = ytDlpManager.clearCookies()

    suspend fun updateEngine(): AppResult<String> = ytDlpManager.updateEngine()

    fun cancelScan(processId: String) = ytDlpManager.cancelProcess(processId)
}
''',
}
