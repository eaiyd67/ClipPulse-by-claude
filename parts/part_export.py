"""FfmpegRunner, SuperChatOverlayRenderer, ClipExporter, and ExportForegroundService."""

FILES = {
    "app/src/main/java/com/clippulse/app/data/export/FfmpegRunner.kt": r'''
package com.clippulse.app.data.export

import android.content.Context
import com.clippulse.app.domain.model.AppResult
import com.clippulse.app.util.ErrorSanitizer
import com.yausername.ffmpeg.FFmpeg
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import java.io.BufferedReader
import java.io.File
import java.io.InputStreamReader
import java.nio.charset.StandardCharsets
import java.util.concurrent.ConcurrentHashMap
import kotlin.coroutines.resume

class FfmpegRunner(private val appContext: Context) {

    private val runningProcesses = ConcurrentHashMap<String, Process>()
    private val timeRegex = Regex("time=(\\d{2}):(\\d{2}):(\\d{2})\\.(\\d{2})")

    fun buildLdLibraryPath(): String {
        val dirs = LinkedHashSet<String>()
        val roots = listOfNotNull(
            File(appContext.noBackupFilesDir, "youtubedl-android/packages"),
            File(appContext.filesDir, "youtubedl-android/packages")
        )
        for (packagesRoot in roots) {
            if (packagesRoot.isDirectory) {
                packagesRoot.listFiles()?.filter { it.isDirectory }?.forEach { pkgDir ->
                    val usrLib = File(pkgDir, "usr/lib")
                    if (usrLib.isDirectory) dirs.add(usrLib.absolutePath)
                    val directLib = File(pkgDir, "lib")
                    if (directLib.isDirectory) dirs.add(directLib.absolutePath)
                }
            }
        }
        val nativeLibDir = appContext.applicationInfo.nativeLibraryDir
        if (!nativeLibDir.isNullOrBlank()) {
            dirs.add(nativeLibDir)
        }
        val existingEnv = System.getenv("LD_LIBRARY_PATH")
        if (!existingEnv.isNullOrBlank()) {
            existingEnv.split(File.pathSeparator).filter { it.isNotBlank() }.forEach { dirs.add(it) }
        }
        return dirs.joinToString(File.pathSeparator)
    }

    fun resolveFfmpegBinary(): File? {
        runCatching { FFmpeg.getInstance().init(appContext) }
        val candidates = listOf(
            File(appContext.noBackupFilesDir, "youtubedl-android/packages/ffmpeg/usr/bin/ffmpeg"),
            File(appContext.filesDir, "youtubedl-android/packages/ffmpeg/usr/bin/ffmpeg"),
            File(appContext.noBackupFilesDir, "youtubedl-android/packages/ffmpeg/bin/ffmpeg"),
            File(appContext.filesDir, "youtubedl-android/packages/ffmpeg/bin/ffmpeg"),
            File(appContext.applicationInfo.nativeLibraryDir, "libffmpeg.so")
        )
        for (cand in candidates) {
            if (cand.exists() && cand.isFile) {
                if (!cand.canExecute()) {
                    runCatching { cand.setExecutable(true) }
                }
                return cand
            }
        }
        val scanRoots = listOf(
            File(appContext.noBackupFilesDir, "youtubedl-android/packages"),
            File(appContext.filesDir, "youtubedl-android/packages")
        )
        for (root in scanRoots) {
            if (!root.isDirectory) continue
            val found = root.walkTopDown()
                .maxDepth(5)
                .firstOrNull { it.isFile && it.name == "ffmpeg" }
            if (found != null) {
                if (!found.canExecute()) runCatching { found.setExecutable(true) }
                return found
            }
        }
        return null
    }

    fun cancel(jobId: String) {
        runningProcesses.remove(jobId)?.let { proc ->
            runCatching { proc.destroy() }
            runCatching { proc.destroyForcibly() }
        }
    }

    suspend fun run(
        args: List<String>,
        expectedDurationSec: Double,
        jobId: String,
        onProgress: (Float) -> Unit
    ): AppResult<String> = withContext(Dispatchers.IO) {
        val binary = resolveFfmpegBinary()
            ?: return@withContext AppResult.Error("FFmpeg binary not found in bundled packages.")

        val command = ArrayList<String>(args.size + 1).apply {
            add(binary.absolutePath)
            addAll(args)
        }

        val pb = ProcessBuilder(command).apply {
            redirectErrorStream(true)
            environment()["LD_LIBRARY_PATH"] = buildLdLibraryPath()
        }

        try {
            val process = pb.start()
            runningProcesses[jobId] = process

            val tailLines = ArrayDeque<String>(24)
            val exitCode = suspendCancellableCoroutine<Int> { cont ->
                cont.invokeOnCancellation {
                    cancel(jobId)
                }
                val readerThread = Thread {
                    try {
                        BufferedReader(InputStreamReader(process.inputStream, StandardCharsets.UTF_8)).use { br ->
                            while (true) {
                                val line = br.readLine() ?: break
                                if (tailLines.size >= 24) tailLines.removeFirst()
                                tailLines.addLast(line)
                                if (expectedDurationSec > 0.5) {
                                    val match = timeRegex.find(line)
                                    if (match != null) {
                                        val h = match.groupValues[1].toDoubleOrNull() ?: 0.0
                                        val m = match.groupValues[2].toDoubleOrNull() ?: 0.0
                                        val s = match.groupValues[3].toDoubleOrNull() ?: 0.0
                                        val cs = match.groupValues[4].toDoubleOrNull() ?: 0.0
                                        val currentSec = h * 3600.0 + m * 60.0 + s + (cs / 100.0)
                                        val ratio = (currentSec / expectedDurationSec).toFloat().coerceIn(0f, 0.99f)
                                        onProgress(ratio)
                                    }
                                }
                            }
                        }
                        val code = process.waitFor()
                        if (cont.isActive) cont.resume(code)
                    } catch (_: Exception) {
                        if (cont.isActive) cont.resume(-1)
                    }
                }
                readerThread.isDaemon = true
                readerThread.start()
            }

            runningProcesses.remove(jobId)
            val logTail = tailLines.joinToString("\n")
            if (exitCode == 0) {
                onProgress(1f)
                AppResult.Success(logTail)
            } else {
                AppResult.Error(
                    ErrorSanitizer.sanitize("FFmpeg exited with code $exitCode: ${tailLines.lastOrNull().orEmpty()}"),
                    code = exitCode
                )
            }
        } catch (e: Exception) {
            runningProcesses.remove(jobId)
            AppResult.Error(ErrorSanitizer.sanitize(e.message, "FFmpeg execution failed."), cause = e)
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/data/export/SuperChatOverlayRenderer.kt": r'''
package com.clippulse.app.data.export

import android.content.Context
import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.RectF
import android.graphics.Typeface
import android.text.Layout
import android.text.StaticLayout
import android.text.TextPaint
import com.clippulse.app.domain.model.AppResult
import com.clippulse.app.domain.model.SuperChatEvent
import com.clippulse.app.util.ErrorSanitizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream

class SuperChatOverlayRenderer(private val appContext: Context) {

    suspend fun renderCardPng(
        event: SuperChatEvent,
        outputFile: File,
        cardWidthPx: Int = 920
    ): AppResult<File> = withContext(Dispatchers.IO) {
        try {
            val padding = 28f
            val headerHeight = 96f
            val radius = 28f

            val msgPaint = TextPaint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.parseColor("#F8FAFC")
                textSize = 34f
                typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.NORMAL)
            }

            val textWidth = (cardWidthPx - (padding * 2f).toInt()).coerceAtLeast(240)
            val cleanMessage = event.message.trim().ifBlank { "Sent a Super Chat" }.take(220)
            val msgLayout = StaticLayout.Builder
                .obtain(cleanMessage, 0, cleanMessage.length, msgPaint, textWidth)
                .setAlignment(Layout.Alignment.ALIGN_NORMAL)
                .setLineSpacing(6f, 1.0f)
                .setMaxLines(4)
                .build()

            val bodyHeight = msgLayout.height.toFloat() + padding * 1.8f
            val totalHeight = (headerHeight + bodyHeight + 8f).toInt().coerceAtLeast(180)

            val bitmap = Bitmap.createBitmap(cardWidthPx, totalHeight, Bitmap.Config.ARGB_8888)
            val canvas = Canvas(bitmap)
            canvas.drawColor(Color.TRANSPARENT)

            val tierRgb = (event.tierColorHex and 0x00FFFFFFL).toInt()
            val tierColor = if (tierRgb == 0) Color.parseColor("#F59E0B") else (0xFF000000.toInt() or tierRgb)

            val cardRect = RectF(4f, 4f, cardWidthPx - 4f, totalHeight - 4f)
            val bodyPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.parseColor("#E616161D")
                style = Paint.Style.FILL
            }
            canvas.drawRoundRect(cardRect, radius, radius, bodyPaint)

            // Header band clipped to top rounded corners
            canvas.save()
            val headerClipPath = android.graphics.Path().apply {
                addRoundRect(
                    cardRect,
                    floatArrayOf(radius, radius, radius, radius, 0f, 0f, 0f, 0f),
                    android.graphics.Path.Direction.CW
                )
            }
            canvas.clipPath(headerClipPath)
            val headerPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = tierColor
                style = Paint.Style.FILL
            }
            canvas.drawRect(cardRect.left, cardRect.top, cardRect.right, cardRect.top + headerHeight, headerPaint)
            canvas.restore()

            val borderPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = tierColor
                style = Paint.Style.STROKE
                strokeWidth = 4f
            }
            canvas.drawRoundRect(cardRect, radius, radius, borderPaint)

            val authorPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.parseColor("#0B0B0F")
                textSize = 34f
                typeface = Typeface.create(Typeface.SANS_SERIF, Typeface.BOLD)
            }
            val amountPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
                color = Color.parseColor("#0B0B0F")
                textSize = 36f
                typeface = Typeface.create(Typeface.MONOSPACE, Typeface.BOLD)
                textAlign = Paint.Align.RIGHT
            }

            val authorText = event.author.trim().ifBlank { "Supporter" }.take(28)
            val amountText = event.amountText.trim().ifBlank { "SUPER CHAT" }.take(18)
            val baselineY = cardRect.top + headerHeight * 0.64f
            canvas.drawText(authorText, cardRect.left + padding, baselineY, authorPaint)
            canvas.drawText(amountText, cardRect.right - padding, baselineY, amountPaint)

            canvas.save()
            canvas.translate(cardRect.left + padding, cardRect.top + headerHeight + padding * 0.8f)
            msgLayout.draw(canvas)
            canvas.restore()

            outputFile.parentFile?.mkdirs()
            FileOutputStream(outputFile).use { fos ->
                bitmap.compress(Bitmap.CompressFormat.PNG, 100, fos)
            }
            bitmap.recycle()
            AppResult.Success(outputFile)
        } catch (e: Exception) {
            AppResult.Error(ErrorSanitizer.sanitize(e.message, "Failed to render Super Chat overlay."), cause = e)
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/data/export/ClipExporter.kt": r'''
package com.clippulse.app.data.export

import android.content.Context
import android.net.Uri
import com.clippulse.app.data.scan.YtDlpManager
import com.clippulse.app.data.storage.HistoryRepository
import com.clippulse.app.data.storage.StorageManager
import com.clippulse.app.domain.model.AppResult
import com.clippulse.app.domain.model.ExportConfig
import com.clippulse.app.domain.model.ExportRecord
import com.clippulse.app.util.ErrorSanitizer
import com.clippulse.app.util.UrlNormalizer
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.io.FileOutputStream
import java.util.Locale
import java.util.UUID

class ClipExporter(
    private val context: Context,
    private val ytDlpManager: YtDlpManager,
    private val ffmpegRunner: FfmpegRunner,
    private val overlayRenderer: SuperChatOverlayRenderer,
    private val storageManager: StorageManager,
    private val historyRepository: HistoryRepository
) {

    fun cancel(jobId: String) {
        ytDlpManager.cancelProcess("dl_$jobId")
        ffmpegRunner.cancel("ff_$jobId")
    }

    suspend fun export(
        config: ExportConfig,
        jobId: String,
        onProgress: (stage: String, progress: Float) -> Unit
    ): AppResult<ExportRecord> = withContext(Dispatchers.IO) {
        val workDir = File(context.cacheDir, "export_${jobId.take(8)}")
        workDir.mkdirs()

        try {
            val clipDuration = config.clip.durationSec.coerceAtLeast(1.0)
            val rawInputFile: File
            val inputAlreadyTrimmed: Boolean

            if (config.metadata.isLocalFile) {
                onProgress("Preparing local video source...", 0.08f)
                val uri = Uri.parse(config.metadata.localUri ?: config.metadata.sourceUrl)
                val copied = File(workDir, "local_source.mp4")
                context.contentResolver.openInputStream(uri)?.use { input ->
                    FileOutputStream(copied).use { output ->
                        input.copyTo(output)
                    }
                } ?: return@withContext AppResult.Error("Could not read local video file.")
                rawInputFile = copied
                inputAlreadyTrimmed = false
            } else {
                onProgress("Downloading clip section...", 0.10f)
                val outTemplate = File(workDir, "section.%(ext)s").absolutePath
                val dlPrimary = ytDlpManager.downloadSection(
                    sourceUrl = config.metadata.sourceUrl,
                    startSec = config.clip.startSec,
                    endSec = config.clip.endSec,
                    outputTemplatePath = outTemplate,
                    useAria2cFallback = false,
                    processId = "dl_$jobId"
                ) { pct, _ ->
                    onProgress("Downloading section (${(pct * 100f).toInt()}%)...", 0.10f + pct * 0.35f)
                }

                val downloaded = when (dlPrimary) {
                    is AppResult.Success -> dlPrimary.data
                    is AppResult.Error -> {
                        onProgress("Retrying section with aria2c fallback...", 0.18f)
                        when (
                            val dlFallback = ytDlpManager.downloadSection(
                                sourceUrl = config.metadata.sourceUrl,
                                startSec = config.clip.startSec,
                                endSec = config.clip.endSec,
                                outputTemplatePath = outTemplate,
                                useAria2cFallback = true,
                                processId = "dl_$jobId"
                            ) { pct, _ ->
                                onProgress("aria2c fallback (${(pct * 100f).toInt()}%)...", 0.18f + pct * 0.27f)
                            }
                        ) {
                            is AppResult.Success -> dlFallback.data
                            is AppResult.Error -> return@withContext dlFallback
                        }
                    }
                }
                rawInputFile = downloaded
                inputAlreadyTrimmed = true
            }

            val superChat = if (config.burnSuperChatOverlay) config.clip.superChat else null
            var overlayPng: File? = null
            if (superChat != null) {
                onProgress("Rendering Super Chat overlay...", 0.48f)
                val pngOut = File(workDir, "superchat_overlay.png")
                val pngWidth = if (config.aspect9x16) 920 else 760
                when (val renderRes = overlayRenderer.renderCardPng(superChat, pngOut, pngWidth)) {
                    is AppResult.Success -> overlayPng = renderRes.data
                    is AppResult.Error -> overlayPng = null
                }
            }

            val renderedMp4 = File(workDir, "final_clip.mp4")
            val canFastCut = config.fastCutBypass &&
                !config.aspect9x16 &&
                overlayPng == null &&
                !config.applyLoudnorm

            if (canFastCut) {
                onProgress("Fast-cut remuxing (stream copy)...", 0.55f)
                val args = buildList {
                    add("-y")
                    if (!inputAlreadyTrimmed) {
                        add("-ss")
                        add(String.format(Locale.US, "%.3f", config.clip.startSec))
                    }
                    add("-i")
                    add(rawInputFile.absolutePath)
                    if (!inputAlreadyTrimmed) {
                        add("-t")
                        add(String.format(Locale.US, "%.3f", clipDuration))
                    }
                    add("-c")
                    add("copy")
                    add("-movflags")
                    add("+faststart")
                    add(renderedMp4.absolutePath)
                }
                val ffRes = ffmpegRunner.run(args, clipDuration, "ff_$jobId") { pct ->
                    onProgress("Fast-cut (${(pct * 100f).toInt()}%)...", 0.55f + pct * 0.35f)
                }
                if (ffRes is AppResult.Error) return@withContext ffRes
            } else {
                onProgress("Encoding clip with FFmpeg...", 0.52f)
                val primaryArgs = buildEncodeArgs(
                    inputFile = rawInputFile,
                    outputFile = renderedMp4,
                    overlayPng = overlayPng,
                    config = config,
                    inputAlreadyTrimmed = inputAlreadyTrimmed,
                    clipDuration = clipDuration,
                    includeLoudnorm = config.applyLoudnorm
                )
                val firstAttempt = ffmpegRunner.run(primaryArgs, clipDuration, "ff_$jobId") { pct ->
                    onProgress("Encoding (${(pct * 100f).toInt()}%)...", 0.52f + pct * 0.38f)
                }
                if (firstAttempt is AppResult.Error) {
                    if (config.applyLoudnorm) {
                        onProgress("Loudnorm fallback — re-encoding audio...", 0.55f)
                        val fallbackArgs = buildEncodeArgs(
                            inputFile = rawInputFile,
                            outputFile = renderedMp4,
                            overlayPng = overlayPng,
                            config = config,
                            inputAlreadyTrimmed = inputAlreadyTrimmed,
                            clipDuration = clipDuration,
                            includeLoudnorm = false
                        )
                        val secondAttempt = ffmpegRunner.run(fallbackArgs, clipDuration, "ff_$jobId") { pct ->
                            onProgress("Encoding fallback (${(pct * 100f).toInt()}%)...", 0.55f + pct * 0.35f)
                        }
                        if (secondAttempt is AppResult.Error) return@withContext secondAttempt
                    } else {
                        return@withContext firstAttempt
                    }
                }
            }

            if (!renderedMp4.exists() || renderedMp4.length() < 1024L) {
                return@withContext AppResult.Error("Rendered MP4 is missing or empty.")
            }

            onProgress("Saving to device storage...", 0.92f)
            val baseName = UrlNormalizer.sanitizeFileName(config.clip.title)
            val suffix = System.currentTimeMillis().toString().takeLast(5)
            val mp4FileName = "ClipPulse_${baseName}_$suffix.mp4"

            val savedClip = when (val saveRes = storageManager.saveExportedClip(renderedMp4, mp4FileName)) {
                is AppResult.Success -> saveRes.data
                is AppResult.Error -> return@withContext saveRes
            }

            var sidecarUri: String? = null
            if (config.writeSidecarTxt) {
                val txtName = "ClipPulse_${baseName}_$suffix.txt"
                val txtContent = buildSidecarText(config, mp4FileName)
                sidecarUri = storageManager.saveSidecarText(txtName, txtContent).getOrNull()
            }

            val record = ExportRecord(
                id = UUID.randomUUID().toString(),
                clipTitle = config.clip.title,
                sourceTitle = config.metadata.title,
                durationSec = clipDuration,
                fileName = mp4FileName,
                contentUri = savedClip.contentUri,
                sidecarUri = sidecarUri,
                fileSizeBytes = savedClip.sizeBytes,
                createdAtMs = System.currentTimeMillis(),
                aspect9x16 = config.aspect9x16
            )
            historyRepository.recordExport(record)
            onProgress("Export complete", 1f)
            AppResult.Success(record)
        } catch (e: Exception) {
            AppResult.Error(ErrorSanitizer.sanitize(e.message, "Export failed unexpectedly."), cause = e)
        } finally {
            runCatching { workDir.deleteRecursively() }
        }
    }

    private fun buildEncodeArgs(
        inputFile: File,
        outputFile: File,
        overlayPng: File?,
        config: ExportConfig,
        inputAlreadyTrimmed: Boolean,
        clipDuration: Double,
        includeLoudnorm: Boolean
    ): List<String> {
        val args = mutableListOf<String>()
        args.add("-y")
        if (!inputAlreadyTrimmed) {
            args.add("-ss")
            args.add(String.format(Locale.US, "%.3f", config.clip.startSec))
        }
        args.add("-i")
        args.add(inputFile.absolutePath)
        if (overlayPng != null) {
            args.add("-i")
            args.add(overlayPng.absolutePath)
        }
        if (!inputAlreadyTrimmed) {
            args.add("-t")
            args.add(String.format(Locale.US, "%.3f", clipDuration))
        }

        val offsetStr = String.format(Locale.US, "%.4f", config.cropOffsetX.toDouble().coerceIn(0.0, 1.0))
        val cropFilter =
            "crop=min(iw\\,ih*9/16):ih:(iw-min(iw\\,ih*9/16))*$offsetStr:0," +
                "scale=1080:1920:force_original_aspect_ratio=decrease," +
                "pad=1080:1920:(ow-iw)/2:(oh-ih)/2:black"

        if (overlayPng != null) {
            val baseVideoChain = if (config.aspect9x16) {
                "[0:v]$cropFilter[base];[base][1:v]overlay=(W-w)/2:110[vout]"
            } else {
                "[0:v]scale=trunc(iw/2)*2:trunc(ih/2)*2[base];[base][1:v]overlay=(W-w)/2:40[vout]"
            }
            args.add("-filter_complex")
            args.add(baseVideoChain)
            args.add("-map")
            args.add("[vout]")
            args.add("-map")
            args.add("0:a?")
        } else if (config.aspect9x16) {
            args.add("-vf")
            args.add(cropFilter)
        } else {
            args.add("-vf")
            args.add("scale=trunc(iw/2)*2:trunc(ih/2)*2")
        }

        if (includeLoudnorm) {
            args.add("-af")
            args.add("loudnorm=I=-14:TP=-1.5:LRA=11")
        }

        args.add("-c:v")
        args.add("libx264")
        args.add("-preset")
        args.add("veryfast")
        args.add("-crf")
        args.add("22")
        args.add("-pix_fmt")
        args.add("yuv420p")
        args.add("-c:a")
        args.add("aac")
        args.add("-b:a")
        args.add("128k")
        args.add("-movflags")
        args.add("+faststart")
        args.add(outputFile.absolutePath)
        return args
    }

    private fun buildSidecarText(config: ExportConfig, mp4FileName: String): String {
        val c = config.clip
        val m = config.metadata
        return buildString {
            appendLine("ClipPulse Export Metadata")
            appendLine("=========================")
            appendLine("File: $mp4FileName")
            appendLine("Clip Title: ${c.title}")
            appendLine("Source: ${m.title}")
            appendLine("Creator: ${m.uploader}")
            appendLine("Source URL: ${m.sourceUrl}")
            appendLine(
                "Window: ${UrlNormalizer.formatPreciseTimestamp(c.startSec)} -> ${UrlNormalizer.formatPreciseTimestamp(c.endSec)} " +
                    String.format(Locale.US, "(%.1fs)", c.durationSec)
            )
            appendLine("Signals: ${c.signals.joinToString(", ") { it.label }}")
            appendLine("Reason: ${c.reason}")
            c.superChat?.let { sc ->
                appendLine()
                appendLine("Super Chat:")
                appendLine("  ${sc.author} (${sc.amountText}): ${sc.message}")
            }
            c.copyPack?.let { pack ->
                appendLine()
                appendLine("Viral Copy Pack:")
                appendLine("Hook: ${pack.hook}")
                appendLine("Titles:")
                pack.titles.forEachIndexed { idx, t -> appendLine("  ${idx + 1}. $t") }
                appendLine("Description: ${pack.description}")
                appendLine("Hashtags: ${pack.hashtags.joinToString(" ")}")
            }
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/service/ExportForegroundService.kt": r'''
package com.clippulse.app.service

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import com.clippulse.app.ClipPulseApplication
import com.clippulse.app.MainActivity
import com.clippulse.app.domain.model.AppResult
import com.clippulse.app.domain.model.ExportConfig
import com.clippulse.app.domain.model.ExportProgress
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.cancel
import kotlinx.coroutines.launch
import java.util.UUID

class ExportForegroundService : Service() {

    private val serviceScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private var activeExportJob: Job? = null
    private var currentJobId: String? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_CANCEL_EXPORT -> {
                val app = application as ClipPulseApplication
                currentJobId?.let { app.container.clipExporter.cancel(it) }
                activeExportJob?.cancel()
                app.container.updateExportProgress(
                    ExportProgress(
                        jobId = currentJobId.orEmpty(),
                        clipTitle = "Export",
                        stage = "Cancelled",
                        progress = 0f,
                        isRunning = false,
                        error = "Export cancelled by user."
                    )
                )
                stopSelfCleanly()
                return START_NOT_STICKY
            }
            ACTION_START_EXPORT -> {
                val app = application as ClipPulseApplication
                val config = app.container.pendingExportConfig
                if (config == null) {
                    stopSelfCleanly()
                    return START_NOT_STICKY
                }
                startExportJob(config)
            }
        }
        return START_NOT_STICKY
    }

    private fun startExportJob(config: ExportConfig) {
        val app = application as ClipPulseApplication
        val jobId = UUID.randomUUID().toString()
        currentJobId = jobId

        val initialNotification = buildNotification(
            title = "Exporting ${config.clip.title}",
            text = "Starting clip pipeline...",
            progressPct = 0,
            ongoing = true
        )

        val fgType = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC
        } else {
            0
        }
        ServiceCompat.startForeground(this, NOTIFICATION_ID, initialNotification, fgType)

        activeExportJob?.cancel()
        activeExportJob = serviceScope.launch {
            app.container.updateExportProgress(
                ExportProgress(
                    jobId = jobId,
                    clipTitle = config.clip.title,
                    stage = "Starting export...",
                    progress = 0.02f,
                    isRunning = true
                )
            )

            val result = app.container.clipExporter.export(config, jobId) { stage, progress ->
                val clamped = progress.coerceIn(0f, 1f)
                app.container.updateExportProgress(
                    ExportProgress(
                        jobId = jobId,
                        clipTitle = config.clip.title,
                        stage = stage,
                        progress = clamped,
                        isRunning = true
                    )
                )
                updateNotification(
                    title = "Exporting ${config.clip.title}",
                    text = stage,
                    progressPct = (clamped * 100f).toInt(),
                    ongoing = true
                )
            }

            when (result) {
                is AppResult.Success -> {
                    val record = result.data
                    app.container.updateExportProgress(
                        ExportProgress(
                            jobId = jobId,
                            clipTitle = record.clipTitle,
                            stage = "Saved ${record.fileName}",
                            progress = 1f,
                            isRunning = false,
                            outputUri = record.contentUri
                        )
                    )
                    updateNotification(
                        title = "Clip Exported",
                        text = record.fileName,
                        progressPct = 100,
                        ongoing = false
                    )
                }
                is AppResult.Error -> {
                    app.container.updateExportProgress(
                        ExportProgress(
                            jobId = jobId,
                            clipTitle = config.clip.title,
                            stage = "Export failed",
                            progress = 0f,
                            isRunning = false,
                            error = result.message
                        )
                    )
                    updateNotification(
                        title = "Export Failed",
                        text = result.message,
                        progressPct = 0,
                        ongoing = false
                    )
                }
            }
            stopSelfCleanly()
        }
    }

    private fun stopSelfCleanly() {
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_DETACH)
        stopSelf()
    }

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            val channel = NotificationChannel(
                CHANNEL_ID,
                "ClipPulse Exports",
                NotificationManager.IMPORTANCE_LOW
            ).apply {
                description = "Shows progress while ClipPulse trims and renders clips"
            }
            nm.createNotificationChannel(channel)
        }
    }

    private fun updateNotification(title: String, text: String, progressPct: Int, ongoing: Boolean) {
        val nm = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        nm.notify(
            if (ongoing) NOTIFICATION_ID else RESULT_NOTIFICATION_ID,
            buildNotification(title, text, progressPct, ongoing)
        )
    }

    private fun buildNotification(
        title: String,
        text: String,
        progressPct: Int,
        ongoing: Boolean
    ): Notification {
        val openIntent = Intent(this, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
        }
        val contentPi = PendingIntent.getActivity(
            this,
            10,
            openIntent,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val builder = NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_download)
            .setContentTitle(title)
            .setContentText(text)
            .setContentIntent(contentPi)
            .setOngoing(ongoing)
            .setOnlyAlertOnce(true)
            .setPriority(NotificationCompat.PRIORITY_LOW)

        if (ongoing) {
            builder.setProgress(100, progressPct.coerceIn(0, 100), progressPct <= 2)
            val cancelIntent = Intent(this, ExportForegroundService::class.java).apply {
                action = ACTION_CANCEL_EXPORT
            }
            val cancelPi = PendingIntent.getService(
                this,
                11,
                cancelIntent,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
            builder.addAction(android.R.drawable.ic_menu_close_clear_cancel, "Cancel", cancelPi)
        } else {
            builder.setAutoCancel(true)
        }

        return builder.build()
    }

    override fun onDestroy() {
        serviceScope.cancel()
        super.onDestroy()
    }

    companion object {
        private const val CHANNEL_ID = "clippulse_export_channel"
        private const val NOTIFICATION_ID = 4101
        private const val RESULT_NOTIFICATION_ID = 4102
        const val ACTION_START_EXPORT = "com.clippulse.app.action.START_EXPORT"
        const val ACTION_CANCEL_EXPORT = "com.clippulse.app.action.CANCEL_EXPORT"

        fun startExport(context: Context, config: ExportConfig) {
            val app = context.applicationContext as ClipPulseApplication
            app.container.pendingExportConfig = config
            val intent = Intent(context, ExportForegroundService::class.java).apply {
                action = ACTION_START_EXPORT
            }
            ContextCompat.startForegroundService(context, intent)
        }

        fun cancelExport(context: Context) {
            val intent = Intent(context, ExportForegroundService::class.java).apply {
                action = ACTION_CANCEL_EXPORT
            }
            context.startService(intent)
        }
    }
}
''',
}
