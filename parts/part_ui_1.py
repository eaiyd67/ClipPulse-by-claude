"""StudioViewModel, HeatmapTimeline, Media3 PreviewPlayerCard with trim/nudge, and ExportOptionsSheet."""

FILES = {
    "app/src/main/java/com/clippulse/app/viewmodel/StudioViewModel.kt": r'''
package com.clippulse.app.viewmodel

import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.ViewModelProvider
import androidx.lifecycle.viewModelScope
import com.clippulse.app.data.PrefsRepo
import com.clippulse.app.data.scan.ScanRepository
import com.clippulse.app.domain.model.AiConfig
import com.clippulse.app.domain.model.AppResult
import com.clippulse.app.domain.model.ClipCandidate
import com.clippulse.app.domain.model.ExportProgress
import com.clippulse.app.domain.model.SignalType
import com.clippulse.app.domain.model.VideoMetadata
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import java.util.UUID

data class StudioUiState(
    val urlInput: String = "",
    val isScanning: Boolean = false,
    val scanStage: String = "",
    val scanError: String? = null,
    val statusBanner: String? = null,
    val clientUsed: String = "",
    val metadata: VideoMetadata? = null,
    val clips: List<ClipCandidate> = emptyList(),
    val selectedFilter: SignalType? = null,
    val selectedClipId: String? = null,
    val cookiesImported: Boolean = false,
    val isUpdatingEngine: Boolean = false,
    val aiConfig: AiConfig = AiConfig(),
    val activeExport: ExportProgress? = null,
    val copyPackClip: ClipCandidate? = null,
    val isGeneratingCopyPack: Boolean = false,
    val exportTargetClip: ClipCandidate? = null,
    val showCustomClipDialog: Boolean = false
) {
    val selectedClip: ClipCandidate?
        get() = clips.firstOrNull { it.id == selectedClipId } ?: clips.firstOrNull()

    val filteredClips: List<ClipCandidate>
        get() = if (selectedFilter == null) {
            clips
        } else {
            clips.filter { it.primarySignal == selectedFilter || selectedFilter in it.signals }
        }
}

class StudioViewModel(
    private val scanRepository: ScanRepository,
    private val prefsRepo: PrefsRepo,
    private val exportProgressFlow: StateFlow<ExportProgress?>
) : ViewModel() {

    private val _uiState = MutableStateFlow(
        StudioUiState(
            cookiesImported = prefsRepo.cookiesPath.value.isNotBlank(),
            aiConfig = prefsRepo.aiConfig.value,
            activeExport = exportProgressFlow.value
        )
    )
    val uiState: StateFlow<StudioUiState> = _uiState.asStateFlow()

    private var scanJob: Job? = null
    private var activeProcessId: String? = null
    private var copyPackJob: Job? = null
    private var engineJob: Job? = null

    init {
        viewModelScope.launch {
            prefsRepo.cookiesPath.collect { path ->
                _uiState.update { it.copy(cookiesImported = path.isNotBlank()) }
            }
        }
        viewModelScope.launch {
            prefsRepo.aiConfig.collect { cfg ->
                _uiState.update { it.copy(aiConfig = cfg) }
            }
        }
        viewModelScope.launch {
            exportProgressFlow.collect { prog ->
                _uiState.update { it.copy(activeExport = prog) }
            }
        }
    }

    fun updateUrlInput(value: String) {
        _uiState.update { it.copy(urlInput = value, scanError = null) }
    }

    fun startScan(overrideUrl: String? = null) {
        val target = (overrideUrl ?: _uiState.value.urlInput).trim()
        if (target.isBlank()) {
            _uiState.update {
                it.copy(scanError = "Enter a YouTube, livestream VOD, Facebook URL, or pick a local video.")
            }
            return
        }
        cancelScan()
        val processId = "scan_${UUID.randomUUID().toString().take(8)}"
        activeProcessId = processId

        scanJob = viewModelScope.launch {
            _uiState.update {
                it.copy(
                    urlInput = target,
                    isScanning = true,
                    scanStage = "Initializing extraction...",
                    scanError = null,
                    statusBanner = null
                )
            }

            when (
                val res = scanRepository.scanUrl(target, processId) { stage ->
                    _uiState.update { it.copy(scanStage = stage) }
                }
            ) {
                is AppResult.Success -> {
                    val outcome = res.data
                    _uiState.update {
                        it.copy(
                            isScanning = false,
                            scanStage = "",
                            scanError = null,
                            clientUsed = outcome.clientUsed,
                            metadata = outcome.metadata,
                            clips = outcome.clips,
                            selectedFilter = null,
                            selectedClipId = outcome.clips.firstOrNull()?.id,
                            statusBanner = outcome.aiWarning ?: "Found ${outcome.clips.size} highlight clips (${outcome.clientUsed})"
                        )
                    }
                }
                is AppResult.Error -> {
                    _uiState.update {
                        it.copy(
                            isScanning = false,
                            scanStage = "",
                            scanError = res.message
                        )
                    }
                }
            }
        }
    }

    fun cancelScan() {
        activeProcessId?.let { scanRepository.cancelScan(it) }
        activeProcessId = null
        scanJob?.cancel()
        scanJob = null
        if (_uiState.value.isScanning) {
            _uiState.update { it.copy(isScanning = false, scanStage = "", statusBanner = "Scan cancelled.") }
        }
    }

    fun selectClip(clipId: String) {
        _uiState.update { it.copy(selectedClipId = clipId) }
    }

    fun selectFilter(type: SignalType?) {
        _uiState.update { current ->
            val nextFilter = if (current.selectedFilter == type) null else type
            val matching = if (nextFilter == null) {
                current.clips
            } else {
                current.clips.filter { it.primarySignal == nextFilter || nextFilter in it.signals }
            }
            val nextSelected = if (matching.any { it.id == current.selectedClipId }) {
                current.selectedClipId
            } else {
                matching.firstOrNull()?.id
            }
            current.copy(selectedFilter = nextFilter, selectedClipId = nextSelected)
        }
    }

    fun updateClipTrim(clipId: String, newStartSec: Double, newEndSec: Double) {
        val duration = _uiState.value.metadata?.durationSec?.coerceAtLeast(2.0) ?: return
        val clampedStart = newStartSec.coerceIn(0.0, (duration - 1.0).coerceAtLeast(0.0))
        val clampedEnd = newEndSec.coerceIn((clampedStart + 1.0).coerceAtMost(duration), duration)
        _uiState.update { state ->
            state.copy(
                clips = state.clips.map { clip ->
                    if (clip.id == clipId) {
                        clip.copy(startSec = clampedStart, endSec = clampedEnd)
                    } else {
                        clip
                    }
                }
            )
        }
    }

    fun nudgeClipStart(clipId: String, deltaSec: Double) {
        val clip = _uiState.value.clips.firstOrNull { it.id == clipId } ?: return
        updateClipTrim(clipId, clip.startSec + deltaSec, clip.endSec)
    }

    fun nudgeClipEnd(clipId: String, deltaSec: Double) {
        val clip = _uiState.value.clips.firstOrNull { it.id == clipId } ?: return
        updateClipTrim(clipId, clip.startSec, clip.endSec + deltaSec)
    }

    fun addCustomClip(title: String, startSec: Double, endSec: Double) {
        val duration = _uiState.value.metadata?.durationSec?.coerceAtLeast(2.0) ?: return
        val safeStart = startSec.coerceIn(0.0, (duration - 1.0).coerceAtLeast(0.0))
        val safeEnd = endSec.coerceIn((safeStart + 1.0).coerceAtMost(duration), duration)
        val cleanTitle = title.trim().ifBlank { "Custom Clip" }
        val newClip = ClipCandidate(
            id = UUID.randomUUID().toString(),
            startSec = safeStart,
            endSec = safeEnd,
            score = 0.90,
            primarySignal = SignalType.AI_PICK,
            signals = listOf(SignalType.AI_PICK),
            title = cleanTitle,
            reason = "Manual custom range",
            isCustom = true
        )
        _uiState.update { state ->
            state.copy(
                clips = listOf(newClip) + state.clips,
                selectedFilter = null,
                selectedClipId = newClip.id,
                showCustomClipDialog = false,
                statusBanner = "Added custom clip \"$cleanTitle\""
            )
        }
    }

    fun openCustomClipDialog(show: Boolean) {
        _uiState.update { it.copy(showCustomClipDialog = show) }
    }

    fun openExportSheet(clip: ClipCandidate?) {
        _uiState.update { it.copy(exportTargetClip = clip) }
    }

    fun openCopyPack(clip: ClipCandidate) {
        val metadata = _uiState.value.metadata ?: return
        copyPackJob?.cancel()
        if (clip.copyPack != null) {
            _uiState.update { it.copy(copyPackClip = clip, isGeneratingCopyPack = false) }
            return
        }
        _uiState.update { it.copy(copyPackClip = clip, isGeneratingCopyPack = true) }
        copyPackJob = viewModelScope.launch {
            when (val res = scanRepository.generateViralCopyPack(clip, metadata)) {
                is AppResult.Success -> {
                    val updatedClip = clip.copy(copyPack = res.data)
                    _uiState.update { state ->
                        state.copy(
                            clips = state.clips.map { if (it.id == clip.id) updatedClip else it },
                            copyPackClip = updatedClip,
                            isGeneratingCopyPack = false
                        )
                    }
                }
                is AppResult.Error -> {
                    _uiState.update {
                        it.copy(
                            isGeneratingCopyPack = false,
                            statusBanner = res.message
                        )
                    }
                }
            }
        }
    }

    fun dismissCopyPack() {
        copyPackJob?.cancel()
        _uiState.update { it.copy(copyPackClip = null, isGeneratingCopyPack = false) }
    }

    fun importCookies(uri: Uri) {
        viewModelScope.launch {
            when (val res = scanRepository.importCookies(uri)) {
                is AppResult.Success -> _uiState.update { it.copy(statusBanner = res.data) }
                is AppResult.Error -> _uiState.update { it.copy(scanError = res.message) }
            }
        }
    }

    fun clearCookies() {
        scanRepository.clearCookies()
        _uiState.update { it.copy(statusBanner = "Cleared cookies.txt") }
    }

    fun updateYtDlpEngine() {
        engineJob?.cancel()
        engineJob = viewModelScope.launch {
            _uiState.update { it.copy(isUpdatingEngine = true, statusBanner = "Checking yt-dlp engine update...") }
            when (val res = scanRepository.updateEngine()) {
                is AppResult.Success -> {
                    _uiState.update { it.copy(isUpdatingEngine = false, statusBanner = res.data) }
                }
                is AppResult.Error -> {
                    _uiState.update { it.copy(isUpdatingEngine = false, scanError = res.message) }
                }
            }
        }
    }

    fun dismissBanner() {
        _uiState.update { it.copy(statusBanner = null, scanError = null) }
    }

    override fun onCleared() {
        cancelScan()
        super.onCleared()
    }

    class Factory(
        private val scanRepository: ScanRepository,
        private val prefsRepo: PrefsRepo,
        private val exportProgressFlow: StateFlow<ExportProgress?>
    ) : ViewModelProvider.Factory {
        @Suppress("UNCHECKED_CAST")
        override fun <T : ViewModel> create(modelClass: Class<T>): T {
            return StudioViewModel(scanRepository, prefsRepo, exportProgressFlow) as T
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/ui/studio/HeatmapTimeline.kt": r'''
package com.clippulse.app.ui.studio

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Size
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.unit.dp
import com.clippulse.app.domain.model.ClipCandidate
import com.clippulse.app.domain.model.HeatmapPoint
import com.clippulse.app.domain.model.SuperChatEvent
import com.clippulse.app.ui.theme.ClipPulseColors
import com.clippulse.app.ui.theme.ClipPulseShapes
import com.clippulse.app.ui.theme.MonoTimestampStyle
import com.clippulse.app.ui.theme.signalColor
import com.clippulse.app.util.UrlNormalizer

@Composable
fun HeatmapTimeline(
    durationSec: Double,
    heatmap: List<HeatmapPoint>,
    superChats: List<SuperChatEvent>,
    clips: List<ClipCandidate>,
    selectedClipId: String?,
    onSelectClip: (String) -> Unit,
    modifier: Modifier = Modifier
) {
    val safeDuration = durationSec.coerceAtLeast(1.0)

    Surface(
        shape = ClipPulseShapes.Card,
        color = ClipPulseColors.Slate,
        border = BorderStroke(1.dp, ClipPulseColors.Hairline),
        modifier = modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(
                    text = "Signal Heatmap Timeline",
                    style = MaterialTheme.typography.titleSmall
                )
                Text(
                    text = "00:00 — ${UrlNormalizer.formatTimestamp(safeDuration)}",
                    style = MonoTimestampStyle,
                    color = ClipPulseColors.TextSecondary
                )
            }

            Canvas(
                modifier = Modifier
                    .fillMaxWidth()
                    .height(74.dp)
                    .pointerInput(clips, safeDuration) {
                        detectTapGestures { offset ->
                            if (size.width <= 0 || clips.isEmpty()) return@detectTapGestures
                            val tapSec = (offset.x.toDouble() / size.width.toDouble()) * safeDuration
                            val hit = clips.firstOrNull { tapSec >= it.startSec && tapSec <= it.endSec }
                                ?: clips.minByOrNull { kotlin.math.abs(((it.startSec + it.endSec) / 2.0) - tapSec) }
                            if (hit != null) onSelectClip(hit.id)
                        }
                    }
            ) {
                val w = size.width
                val h = size.height
                val baseY = h - 8f

                // Baseline track
                drawLine(
                    color = ClipPulseColors.Hairline,
                    start = Offset(0f, baseY),
                    end = Offset(w, baseY),
                    strokeWidth = 2f
                )

                // Draw clip candidate spans
                for (clip in clips) {
                    val x1 = ((clip.startSec / safeDuration).toFloat().coerceIn(0f, 1f)) * w
                    val x2 = ((clip.endSec / safeDuration).toFloat().coerceIn(0f, 1f)) * w
                    val spanW = (x2 - x1).coerceAtLeast(4f)
                    val isSelected = clip.id == selectedClipId
                    val color = signalColor(clip.primarySignal)
                    drawRect(
                        color = color.copy(alpha = if (isSelected) 0.34f else 0.16f),
                        topLeft = Offset(x1, 4f),
                        size = Size(spanW, baseY - 4f)
                    )
                    if (isSelected) {
                        drawLine(
                            color = color,
                            start = Offset(x1, 4f),
                            end = Offset(x1 + spanW, 4f),
                            strokeWidth = 4f
                        )
                    }
                }

                // Draw YouTube replay heatmap curve if present
                if (heatmap.size >= 2) {
                    val linePath = Path()
                    val fillPath = Path()
                    heatmap.forEachIndexed { index, pt ->
                        val cx = (((pt.startSec + pt.endSec) / 2.0) / safeDuration).toFloat().coerceIn(0f, 1f) * w
                        val cy = baseY - (pt.value.toFloat().coerceIn(0f, 1f) * (baseY - 12f))
                        if (index == 0) {
                            linePath.moveTo(cx, cy)
                            fillPath.moveTo(cx, baseY)
                            fillPath.lineTo(cx, cy)
                        } else {
                            linePath.lineTo(cx, cy)
                            fillPath.lineTo(cx, cy)
                        }
                    }
                    val lastPt = heatmap.last()
                    val lastX = (((lastPt.startSec + lastPt.endSec) / 2.0) / safeDuration).toFloat().coerceIn(0f, 1f) * w
                    fillPath.lineTo(lastX, baseY)
                    fillPath.close()

                    drawPath(
                        path = fillPath,
                        brush = Brush.verticalGradient(
                            colors = listOf(
                                ClipPulseColors.CrimsonHeatmap.copy(alpha = 0.32f),
                                ClipPulseColors.CrimsonHeatmap.copy(alpha = 0.02f)
                            )
                        )
                    )
                    drawPath(
                        path = linePath,
                        color = ClipPulseColors.CrimsonHeatmap,
                        style = Stroke(width = 2.5f, cap = StrokeCap.Round)
                    )
                }

                // Draw Super Chat gold pins
                for (sc in superChats) {
                    val x = ((sc.timestampSec / safeDuration).toFloat().coerceIn(0f, 1f)) * w
                    drawLine(
                        color = ClipPulseColors.GoldSuperChat,
                        start = Offset(x, 8f),
                        end = Offset(x, baseY),
                        strokeWidth = 2f
                    )
                    drawCircle(
                        color = ClipPulseColors.GoldSuperChat,
                        radius = 4.5f,
                        center = Offset(x, 10f)
                    )
                }
            }
        }
    }
}
''',

    "app/src/main/java/com/clippulse/app/ui/studio/PreviewPlayerCard.kt": r'''
package com.clippulse.app.ui.studio

import android.net.Uri
import android.view.ViewGroup
import android.widget.FrameLayout
import androidx.annotation.OptIn
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ContentCut
import androidx.compose.material.icons.filled.Download
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Replay
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedButton
import androidx.compose.material3.RangeSlider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.common.util.UnstableApi
import androidx.media3.datasource.DefaultDataSource
import androidx.media3.datasource.okhttp.OkHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.DefaultMediaSourceFactory
import androidx.media3.ui.PlayerView
import com.clippulse.app.domain.model.ClipCandidate
import com.clippulse.app.domain.model.VideoMetadata
import com.clippulse.app.ui.theme.ClipPulseColors
import com.clippulse.app.ui.theme.ClipPulseShapes
import com.clippulse.app.ui.theme.MonoTimestampStyle
import com.clippulse.app.ui.theme.signalColor
import com.clippulse.app.util.UrlNormalizer
import kotlinx.coroutines.delay
import okhttp3.Call
import okhttp3.OkHttpClient
import java.util.Locale

@OptIn(UnstableApi::class)
@Composable
fun PreviewPlayerCard(
    metadata: VideoMetadata,
    clip: ClipCandidate,
    okHttpClient: OkHttpClient,
    onTrimChanged: (startSec: Double, endSec: Double) -> Unit,
    onNudgeStart: (Double) -> Unit,
    onNudgeEnd: (Double) -> Unit,
    onExportClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    val context = LocalContext.current
    var isPlaying by remember { mutableStateOf(false) }
    var currentPosMs by remember { mutableLongStateOf((clip.startSec * 1000.0).toLong()) }

    val exoPlayer = remember(metadata.previewStreamUrl, metadata.streamHeaders) {
        val httpFactory = OkHttpDataSource.Factory(okHttpClient as Call.Factory).apply {
            if (metadata.streamHeaders.isNotEmpty()) {
                setDefaultRequestProperties(metadata.streamHeaders)
            }
        }
        val dataSourceFactory = DefaultDataSource.Factory(context, httpFactory)
        val mediaSourceFactory = DefaultMediaSourceFactory(context)
            .setDataSourceFactory(dataSourceFactory)

        ExoPlayer.Builder(context)
            .setMediaSourceFactory(mediaSourceFactory)
            .build()
            .apply {
                val uri = Uri.parse(metadata.previewStreamUrl)
                setMediaItem(MediaItem.fromUri(uri))
                prepare()
                playWhenReady = false
            }
    }

    DisposableEffect(exoPlayer) {
        val listener = object : Player.Listener {
            override fun onIsPlayingChanged(playing: Boolean) {
                isPlaying = playing
            }
        }
        exoPlayer.addListener(listener)
        onDispose {
            exoPlayer.removeListener(listener)
            exoPlayer.release()
        }
    }

    // Seek player when selected clip changes
    LaunchedEffect(clip.id) {
        val startMs = (clip.startSec * 1000.0).toLong().coerceAtLeast(0L)
        exoPlayer.seekTo(startMs)
        currentPosMs = startMs
    }

    // Keep playback looped inside the trimmed [startSec, endSec] range
    LaunchedEffect(exoPlayer, clip.id, clip.startSec, clip.endSec) {
        while (true) {
            val pos = exoPlayer.currentPosition
            currentPosMs = pos
            val startMs = (clip.startSec * 1000.0).toLong().coerceAtLeast(0L)
            val endMs = (clip.endSec * 1000.0).toLong().coerceAtLeast(startMs + 500L)
            if (exoPlayer.isPlaying && pos >= endMs) {
                exoPlayer.seekTo(startMs)
            }
            delay(200L)
        }
    }

    val safeMax = metadata.durationSec.toFloat().coerceAtLeast(2f)
    val clampedStart = clip.startSec.toFloat().coerceIn(0f, (safeMax - 1f).coerceAtLeast(0f))
    val clampedEnd = clip.endSec.toFloat().coerceIn((clampedStart + 1f).coerceAtMost(safeMax), safeMax)
    val accent = signalColor(clip.primarySignal)

    Surface(
        shape = ClipPulseShapes.Card,
        color = ClipPulseColors.Slate,
        border = BorderStroke(1.dp, ClipPulseColors.Hairline),
        modifier = modifier.fillMaxWidth()
    ) {
        Column(
            modifier = Modifier.padding(14.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        text = clip.title,
                        style = MaterialTheme.typography.titleMedium,
                        maxLines = 1,
                        overflow = TextOverflow.Ellipsis
                    )
                    Text(
                        text = String.format(
                            Locale.US,
                            "Preview %s • Length %.1fs",
                            UrlNormalizer.formatTimestamp(currentPosMs.toDouble() / 1000.0),
                            clip.durationSec
                        ),
                        style = MonoTimestampStyle,
                        color = accent
                    )
                }
                Row(horizontalArrangement = Arrangement.spacedBy(4.dp)) {
                    IconButton(
                        onClick = {
                            val startMs = (clip.startSec * 1000.0).toLong().coerceAtLeast(0L)
                            exoPlayer.seekTo(startMs)
                            exoPlayer.playWhenReady = true
                        },
                        modifier = Modifier.size(48.dp)
                    ) {
                        Icon(
                            Icons.Default.Replay,
                            contentDescription = "Replay clip window",
                            tint = ClipPulseColors.TextSecondary
                        )
                    }
                    IconButton(
                        onClick = {
                            if (exoPlayer.isPlaying) {
                                exoPlayer.pause()
                            } else {
                                val startMs = (clip.startSec * 1000.0).toLong().coerceAtLeast(0L)
                                val endMs = (clip.endSec * 1000.0).toLong()
                                if (exoPlayer.currentPosition < startMs || exoPlayer.currentPosition >= endMs) {
                                    exoPlayer.seekTo(startMs)
                                }
                                exoPlayer.play()
                            }
                        },
                        modifier = Modifier.size(48.dp)
                    ) {
                        Icon(
                            imageVector = if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                            contentDescription = if (isPlaying) "Pause preview" else "Play preview",
                            tint = ClipPulseColors.Indigo
                        )
                    }
                }
            }

            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .aspectRatio(16f / 9f)
                    .background(Color.Black, ClipPulseShapes.Chip)
            ) {
                AndroidView(
                    factory = { ctx ->
                        PlayerView(ctx).apply {
                            player = exoPlayer
                            useController = false
                            layoutParams = FrameLayout.LayoutParams(
                                ViewGroup.LayoutParams.MATCH_PARENT,
                                ViewGroup.LayoutParams.MATCH_PARENT
                            )
                        }
                    },
                    update = { view ->
                        if (view.player !== exoPlayer) {
                            view.player = exoPlayer
                        }
                    },
                    modifier = Modifier.fillMaxSize()
                )
            }

            Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
                Row(
                    modifier = Modifier.fillMaxWidth(),
                    horizontalArrangement = Arrangement.SpaceBetween
                ) {
                    Text(
                        text = "IN ${UrlNormalizer.formatTimestamp(clampedStart.toDouble())}",
                        style = MonoTimestampStyle,
                        color = ClipPulseColors.TextPrimary
                    )
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(
                            Icons.Default.ContentCut,
                            contentDescription = null,
                            tint = ClipPulseColors.TextMuted,
                            modifier = Modifier.size(14.dp)
                        )
                        Spacer(Modifier.width(4.dp))
                        Text(
                            text = "Drag to trim",
                            style = MaterialTheme.typography.bodySmall
                        )
                    }
                    Text(
                        text = "OUT ${UrlNormalizer.formatTimestamp(clampedEnd.toDouble())}",
                        style = MonoTimestampStyle,
                        color = ClipPulseColors.TextPrimary
                    )
                }

                RangeSlider(
                    value = clampedStart..clampedEnd,
                    onValueChange = { range ->
                        val nextStart = range.start.coerceIn(0f, (safeMax - 1f).coerceAtLeast(0f))
                        val nextEnd = range.endInclusive.coerceIn((nextStart + 1f).coerceAtMost(safeMax), safeMax)
                        onTrimChanged(nextStart.toDouble(), nextEnd.toDouble())
                    },
                    onValueChangeFinished = {
                        val seekMs = (clip.startSec * 1000.0).toLong().coerceAtLeast(0L)
                        exoPlayer.seekTo(seekMs)
                    },
                    valueRange = 0f..safeMax,
                    colors = SliderDefaults.colors(
                        thumbColor = accent,
                        activeTrackColor = accent,
                        inactiveTrackColor = ClipPulseColors.Hairline
                    )
                )
            }

            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(6.dp)
            ) {
                NudgeButton(
                    label = "In -1s",
                    onClick = {
                        onNudgeStart(-1.0)
                        exoPlayer.seekTo(((clip.startSec - 1.0).coerceAtLeast(0.0) * 1000.0).toLong())
                    },
                    modifier = Modifier.weight(1f)
                )
                NudgeButton(
                    label = "In +1s",
                    onClick = {
                        onNudgeStart(1.0)
                        exoPlayer.seekTo(((clip.startSec + 1.0) * 1000.0).toLong())
                    },
                    modifier = Modifier.weight(1f)
                )
                NudgeButton(
                    label = "Out -1s",
                    onClick = { onNudgeEnd(-1.0) },
                    modifier = Modifier.weight(1f)
                )
                NudgeButton(
                    label = "Out +1s",
                    onClick = { onNudgeEnd(1.0) },
                    modifier = Modifier.weight(1f)
                )
            }

            Button(
                onClick = {
                    exoPlayer.pause()
                    onExportClick()
                },
                shape = ClipPulseShapes.Chip,
                colors = ButtonDefaults.buttonColors(containerColor = ClipPulseColors.Indigo),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(48.dp)
            ) {
                Icon(Icons.Default.Download, contentDescription = null, modifier = Modifier.size(18.dp))
                Spacer(Modifier.width(8.dp))
                Text(
                    text = String.format(Locale.US, "Export Clip (%.1fs)", clip.durationSec),
                    fontWeight = FontWeight.SemiBold
                )
            }
        }
    }
}

@Composable
private fun NudgeButton(
    label: String,
    onClick: () -> Unit,
    modifier: Modifier = Modifier
) {
    OutlinedButton(
        onClick = onClick,
        shape = ClipPulseShapes.Chip,
        border = BorderStroke(1.dp, ClipPulseColors.Hairline),
        contentPadding = PaddingValues(horizontal = 4.dp, vertical = 0.dp),
        modifier = modifier.height(48.dp)
    ) {
        Text(
            text = label,
            style = MonoTimestampStyle,
            color = ClipPulseColors.TextPrimary,
            maxLines = 1
        )
    }
}
''',

    "app/src/main/java/com/clippulse/app/ui/studio/ExportOptionsSheet.kt": r'''
package com.clippulse.app.ui.studio

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Download
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.Slider
import androidx.compose.material3.SliderDefaults
import androidx.compose.material3.Surface
import androidx.compose.material3.Switch
import androidx.compose.material3.SwitchDefaults
import androidx.compose.material3.Text
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableFloatStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.clippulse.app.domain.model.ClipCandidate
import com.clippulse.app.domain.model.ExportConfig
import com.clippulse.app.domain.model.VideoMetadata
import com.clippulse.app.ui.theme.ClipPulseColors
import com.clippulse.app.ui.theme.ClipPulseShapes
import com.clippulse.app.ui.theme.MonoTimestampStyle
import com.clippulse.app.util.UrlNormalizer
import java.util.Locale

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ExportOptionsSheet(
    clip: ClipCandidate,
    metadata: VideoMetadata,
    onDismiss: () -> Unit,
    onStartExport: (ExportConfig) -> Unit
) {
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    var aspect9x16 by remember(clip.id) { mutableStateOf(true) }
    var cropOffsetX by remember(clip.id) { mutableFloatStateOf(0.5f) }
    var fastCutBypass by remember(clip.id) { mutableStateOf(false) }
    var burnSuperChat by remember(clip.id) { mutableStateOf(clip.superChat != null) }
    var applyLoudnorm by remember(clip.id) { mutableStateOf(true) }
    var writeSidecar by remember(clip.id) { mutableStateOf(true) }

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
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            Text(
                text = "Export Settings",
                style = MaterialTheme.typography.titleLarge
            )
            Text(
                text = "${clip.title} • ${UrlNormalizer.formatTimestamp(clip.startSec)} → ${UrlNormalizer.formatTimestamp(clip.endSec)} (${String.format(Locale.US, "%.1fs", clip.durationSec)})",
                style = MonoTimestampStyle,
                color = ClipPulseColors.CyanAiPick
            )

            ToggleRow(
                title = "9:16 Vertical Shorts Crop (1080×1920)",
                subtitle = "Disable to keep original aspect ratio",
                checked = aspect9x16,
                onCheckedChange = { enabled ->
                    aspect9x16 = enabled
                    if (enabled) fastCutBypass = false
                }
            )

            if (aspect9x16) {
                Surface(
                    shape = ClipPulseShapes.Card,
                    color = ClipPulseColors.Elevated,
                    border = BorderStroke(1.dp, ClipPulseColors.Hairline),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(14.dp),
                        verticalArrangement = Arrangement.spacedBy(4.dp)
                    ) {
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text("Horizontal Crop Offset", style = MaterialTheme.typography.titleSmall)
                            Text(
                                text = String.format(Locale.US, "%d%%", (cropOffsetX * 100f).toInt()),
                                style = MonoTimestampStyle,
                                color = ClipPulseColors.Indigo
                            )
                        }
                        Slider(
                            value = cropOffsetX.coerceIn(0f, 1f),
                            onValueChange = { cropOffsetX = it.coerceIn(0f, 1f) },
                            valueRange = 0f..1f,
                            colors = SliderDefaults.colors(
                                thumbColor = ClipPulseColors.Indigo,
                                activeTrackColor = ClipPulseColors.Indigo,
                                inactiveTrackColor = ClipPulseColors.Hairline
                            )
                        )
                        Row(
                            modifier = Modifier.fillMaxWidth(),
                            horizontalArrangement = Arrangement.SpaceBetween
                        ) {
                            Text("Left", style = MaterialTheme.typography.bodySmall)
                            Text("Center", style = MaterialTheme.typography.bodySmall)
                            Text("Right", style = MaterialTheme.typography.bodySmall)
                        }
                    }
                }
            }

            ToggleRow(
                title = "Fast-Cut Stream Copy Bypass",
                subtitle = "Instant remux without re-encoding (original aspect, no overlay/loudnorm)",
                checked = fastCutBypass,
                onCheckedChange = { enabled ->
                    fastCutBypass = enabled
                    if (enabled) {
                        aspect9x16 = false
                        burnSuperChat = false
                        applyLoudnorm = false
                    }
                }
            )

            if (clip.superChat != null) {
                ToggleRow(
                    title = "Burn Super Chat Overlay (${clip.superChat.amountText})",
                    subtitle = "${clip.superChat.author}: ${clip.superChat.message.take(64)}",
                    checked = burnSuperChat,
                    onCheckedChange = { enabled ->
                        burnSuperChat = enabled
                        if (enabled) fastCutBypass = false
                    }
                )
            }

            ToggleRow(
                title = "Audio Loudnorm (-14 LUFS)",
                subtitle = "Broadcast loudness normalization with automatic AAC fallback",
                checked = applyLoudnorm,
                onCheckedChange = { enabled ->
                    applyLoudnorm = enabled
                    if (enabled) fastCutBypass = false
                }
            )

            ToggleRow(
                title = "Write Sidecar .TXT Metadata",
                subtitle = "Saves timestamps, source link, and viral copy pack alongside MP4",
                checked = writeSidecar,
                onCheckedChange = { writeSidecar = it }
            )

            Spacer(Modifier.height(4.dp))

            Button(
                onClick = {
                    onStartExport(
                        ExportConfig(
                            clip = clip,
                            metadata = metadata,
                            aspect9x16 = aspect9x16,
                            cropOffsetX = cropOffsetX.coerceIn(0f, 1f),
                            fastCutBypass = fastCutBypass,
                            burnSuperChatOverlay = burnSuperChat && clip.superChat != null,
                            applyLoudnorm = applyLoudnorm,
                            writeSidecarTxt = writeSidecar
                        )
                    )
                },
                shape = ClipPulseShapes.Chip,
                colors = ButtonDefaults.buttonColors(containerColor = ClipPulseColors.Indigo),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(50.dp)
            ) {
                Icon(Icons.Default.Download, contentDescription = null)
                Spacer(Modifier.width(8.dp))
                Text("Start Background Export", fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

@Composable
private fun ToggleRow(
    title: String,
    subtitle: String,
    checked: Boolean,
    onCheckedChange: (Boolean) -> Unit
) {
    Surface(
        shape = ClipPulseShapes.Card,
        color = ClipPulseColors.Elevated,
        border = BorderStroke(1.dp, ClipPulseColors.Hairline),
        modifier = Modifier.fillMaxWidth()
    ) {
        Row(
            modifier = Modifier
                .fillMaxWidth()
                .padding(horizontal = 14.dp, vertical = 10.dp),
            horizontalArrangement = Arrangement.SpaceBetween,
            verticalAlignment = Alignment.CenterVertically
        ) {
            Column(
                modifier = Modifier
                    .weight(1f)
                    .padding(end = 10.dp)
            ) {
                Text(text = title, style = MaterialTheme.typography.titleSmall)
                Text(text = subtitle, style = MaterialTheme.typography.bodySmall)
            }
            Switch(
                checked = checked,
                onCheckedChange = onCheckedChange,
                colors = SwitchDefaults.colors(
                    checkedThumbColor = Color.White,
                    checkedTrackColor = ClipPulseColors.Indigo
                )
            )
        }
    }
}
''',
}
