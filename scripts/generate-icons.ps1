param(
    [string]$Root = (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path))
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing

function New-RoundedPath {
    param([float]$X, [float]$Y, [float]$Width, [float]$Height, [float]$Radius)
    $path = New-Object System.Drawing.Drawing2D.GraphicsPath
    $diameter = $Radius * 2
    $path.AddArc($X, $Y, $diameter, $diameter, 180, 90)
    $path.AddArc($X + $Width - $diameter, $Y, $diameter, $diameter, 270, 90)
    $path.AddArc($X + $Width - $diameter, $Y + $Height - $diameter, $diameter, $diameter, 0, 90)
    $path.AddArc($X, $Y + $Height - $diameter, $diameter, $diameter, 90, 90)
    $path.CloseFigure()
    return $path
}

function New-Canvas {
    param([int]$Size)
    $bitmap = New-Object System.Drawing.Bitmap $Size, $Size, ([System.Drawing.Imaging.PixelFormat]::Format32bppArgb)
    $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
    $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
    $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
    $graphics.PixelOffsetMode = [System.Drawing.Drawing2D.PixelOffsetMode]::HighQuality
    return @($bitmap, $graphics)
}

function Save-Icon {
    param([System.Drawing.Bitmap]$Bitmap, [System.Drawing.Graphics]$Graphics, [string]$Path)
    $Graphics.Dispose()
    $Bitmap.Save($Path, [System.Drawing.Imaging.ImageFormat]::Png)
    $Bitmap.Dispose()
}

function Draw-MediaOverlayIcon {
    param([int]$Size, [string]$Path)
    $canvas = New-Canvas $Size
    $bitmap = $canvas[0]
    $g = $canvas[1]
    $s = $Size / 130.0

    $outer = New-RoundedPath 2 2 ($Size - 4) ($Size - 4) (24 * $s)
    $bgBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush (
        (New-Object System.Drawing.PointF 0, 0),
        (New-Object System.Drawing.PointF $Size, $Size),
        ([System.Drawing.Color]::FromArgb(255, 21, 147, 218)),
        ([System.Drawing.Color]::FromArgb(255, 20, 42, 85))
    )
    $g.FillPath($bgBrush, $outer)

    $screen = New-RoundedPath (16*$s) (27*$s) (98*$s) (68*$s) (9*$s)
    $screenBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(245, 5, 17, 32))
    $borderPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 190, 234, 255)), (4*$s)
    $g.FillPath($screenBrush, $screen)
    $g.DrawPath($borderPen, $screen)

    $preview = New-RoundedPath (26*$s) (38*$s) (47*$s) (31*$s) (5*$s)
    $cyanBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 47, 174, 224))
    $g.FillPath($cyanBrush, $preview)
    $play = New-Object System.Drawing.Drawing2D.GraphicsPath
    $play.AddPolygon([System.Drawing.PointF[]]@(
        (New-Object System.Drawing.PointF (45*$s), (44*$s)),
        (New-Object System.Drawing.PointF (45*$s), (64*$s)),
        (New-Object System.Drawing.PointF (62*$s), (54*$s))
    ))
    $whiteBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::White)
    $g.FillPath($whiteBrush, $play)

    $linePen = New-Object System.Drawing.Pen ([System.Drawing.Color]::White), (4*$s)
    $linePen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $linePen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $g.DrawLine($linePen, 84*$s, 42*$s, 105*$s, 42*$s)
    $g.DrawLine($linePen, 105*$s, 42*$s, 105*$s, 63*$s)
    $g.DrawLine($linePen, 105*$s, 42*$s, 97*$s, 50*$s)
    $g.DrawLine($linePen, 105*$s, 42*$s, 97*$s, 42*$s)

    $accentPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 102, 214, 255)), (4*$s)
    $accentPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $accentPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $g.DrawLine($accentPen, 29*$s, 83*$s, 101*$s, 83*$s)
    $g.DrawLine($borderPen, 46*$s, 108*$s, 84*$s, 108*$s)

    Save-Icon $bitmap $g $Path
    $outer.Dispose(); $bgBrush.Dispose(); $screen.Dispose(); $screenBrush.Dispose(); $borderPen.Dispose()
    $preview.Dispose(); $cyanBrush.Dispose(); $play.Dispose(); $whiteBrush.Dispose(); $linePen.Dispose(); $accentPen.Dispose()
}

function Draw-CameraIcon {
    param([int]$Size, [string]$Path)
    $canvas = New-Canvas $Size
    $bitmap = $canvas[0]
    $g = $canvas[1]
    $s = $Size / 130.0

    $outer = New-RoundedPath 2 2 ($Size - 4) ($Size - 4) (24*$s)
    $bgBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush (
        (New-Object System.Drawing.PointF 0, 0),
        (New-Object System.Drawing.PointF $Size, $Size),
        ([System.Drawing.Color]::FromArgb(255, 15, 27, 42)),
        ([System.Drawing.Color]::FromArgb(255, 5, 10, 18))
    )
    $g.FillPath($bgBrush, $outer)

    $body = New-RoundedPath (14*$s) (22*$s) (102*$s) (71*$s) (11*$s)
    $bodyBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 24, 43, 61))
    $bluePen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 91, 186, 255)), (5*$s)
    $g.FillPath($bodyBrush, $body)
    $g.DrawPath($bluePen, $body)

    $lensOuter = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 217, 241, 255))
    $lensMid = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 7, 17, 29))
    $lensBlue = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 91, 186, 255))
    $g.FillEllipse($lensOuter, 37*$s, 29*$s, 56*$s, 56*$s)
    $g.FillEllipse($lensMid, 44*$s, 36*$s, 42*$s, 42*$s)
    $g.FillEllipse($lensBlue, 56*$s, 48*$s, 18*$s, 18*$s)
    $shine = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(190, 255, 255, 255))
    $g.FillEllipse($shine, 59*$s, 50*$s, 5*$s, 5*$s)

    $standPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 217, 241, 255)), (7*$s)
    $standPen.StartCap = [System.Drawing.Drawing2D.LineCap]::Round
    $standPen.EndCap = [System.Drawing.Drawing2D.LineCap]::Round
    $g.DrawLine($standPen, 52*$s, 94*$s, 52*$s, 109*$s)
    $g.DrawLine($standPen, 78*$s, 94*$s, 78*$s, 109*$s)
    $g.DrawLine($standPen, 39*$s, 111*$s, 91*$s, 111*$s)

    Save-Icon $bitmap $g $Path
    $outer.Dispose(); $bgBrush.Dispose(); $body.Dispose(); $bodyBrush.Dispose(); $bluePen.Dispose()
    $lensOuter.Dispose(); $lensMid.Dispose(); $lensBlue.Dispose(); $shine.Dispose(); $standPen.Dispose()
}

function Draw-RemoteMapperIcon {
    param([int]$Size, [string]$Path)
    $canvas = New-Canvas $Size
    $bitmap = $canvas[0]
    $g = $canvas[1]
    $s = $Size / 130.0

    $outer = New-RoundedPath 2 2 ($Size - 4) ($Size - 4) (24*$s)
    $bgBrush = New-Object System.Drawing.Drawing2D.LinearGradientBrush (
        (New-Object System.Drawing.PointF 0, 0),
        (New-Object System.Drawing.PointF $Size, $Size),
        ([System.Drawing.Color]::FromArgb(255, 101, 221, 255)),
        ([System.Drawing.Color]::FromArgb(255, 32, 88, 176))
    )
    $g.FillPath($bgBrush, $outer)

    $remote = New-RoundedPath (38*$s) (13*$s) (54*$s) (104*$s) (19*$s)
    $remoteBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 9, 19, 31))
    $remotePen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 225, 245, 255)), (4*$s)
    $g.FillPath($remoteBrush, $remote)
    $g.DrawPath($remotePen, $remote)

    $buttonBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 101, 221, 255))
    $buttonDim = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 72, 101, 125))
    $g.FillEllipse($buttonBrush, 57*$s, 24*$s, 16*$s, 16*$s)
    $g.FillEllipse($buttonDim, 48*$s, 50*$s, 9*$s, 9*$s)
    $g.FillEllipse($buttonDim, 61*$s, 50*$s, 9*$s, 9*$s)
    $g.FillEllipse($buttonDim, 74*$s, 50*$s, 9*$s, 9*$s)
    $g.FillEllipse($buttonDim, 48*$s, 64*$s, 9*$s, 9*$s)
    $g.FillEllipse($buttonBrush, 61*$s, 64*$s, 9*$s, 9*$s)
    $g.FillEllipse($buttonDim, 74*$s, 64*$s, 9*$s, 9*$s)
    $g.FillEllipse($buttonDim, 48*$s, 78*$s, 9*$s, 9*$s)
    $g.FillEllipse($buttonDim, 61*$s, 78*$s, 9*$s, 9*$s)
    $g.FillEllipse($buttonDim, 74*$s, 78*$s, 9*$s, 9*$s)
    $g.FillEllipse($buttonBrush, 54*$s, 94*$s, 22*$s, 11*$s)

    Save-Icon $bitmap $g $Path
    $outer.Dispose(); $bgBrush.Dispose(); $remote.Dispose(); $remoteBrush.Dispose(); $remotePen.Dispose()
    $buttonBrush.Dispose(); $buttonDim.Dispose()
}

$mediaDir = Join-Path $Root 'apps\media-overlay'
$cameraDir = Join-Path $Root 'apps\camera-viewer'
$remoteDir = Join-Path $Root 'apps\remote-mapper'
$launcherDir = Join-Path $Root 'apps\launcher'
foreach ($size in 80, 130) {
    $name = if ($size -eq 80) { 'icon.png' } else { 'icon-large.png' }
    Draw-MediaOverlayIcon $size (Join-Path $mediaDir $name)
    Draw-CameraIcon $size (Join-Path $cameraDir $name)
    Draw-RemoteMapperIcon $size (Join-Path $remoteDir $name)
}

$splash = New-Object System.Drawing.Bitmap 1920, 1080, ([System.Drawing.Imaging.PixelFormat]::Format24bppRgb)
$splashGraphics = [System.Drawing.Graphics]::FromImage($splash)
$splashGraphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::AntiAlias
$splashGraphics.TextRenderingHint = [System.Drawing.Text.TextRenderingHint]::AntiAliasGridFit
$splashGraphics.Clear([System.Drawing.Color]::FromArgb(255, 3, 8, 13))
$tileCyan = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 117, 216, 255))
$tileWhite = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 238, 248, 255))
$hintBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 126, 157, 177))
$hintFont = New-Object System.Drawing.Font 'Segoe UI', 21, ([System.Drawing.FontStyle]::Regular), ([System.Drawing.GraphicsUnit]::Pixel)
$tileSize = 72
$tileGap = 14
$iconLeft = 960 - $tileSize - ($tileGap / 2)
$iconTop = 414
$tile1 = New-RoundedPath $iconLeft $iconTop $tileSize $tileSize 14
$tile2 = New-RoundedPath ($iconLeft + $tileSize + $tileGap) $iconTop $tileSize $tileSize 14
$tile3 = New-RoundedPath $iconLeft ($iconTop + $tileSize + $tileGap) $tileSize $tileSize 14
$tile4 = New-RoundedPath ($iconLeft + $tileSize + $tileGap) ($iconTop + $tileSize + $tileGap) $tileSize $tileSize 14
$splashGraphics.FillPath($tileCyan, $tile1)
$splashGraphics.FillPath($tileWhite, $tile2)
$splashGraphics.FillPath($tileWhite, $tile3)
$splashGraphics.FillPath($tileCyan, $tile4)
$titleFormat = New-Object System.Drawing.StringFormat
$titleFormat.Alignment = [System.Drawing.StringAlignment]::Center
$splashGraphics.DrawString('Betöltés…', $hintFont, $hintBrush, (New-Object System.Drawing.RectangleF 760, 620, 400, 40), $titleFormat)
$tile1.Dispose(); $tile2.Dispose(); $tile3.Dispose(); $tile4.Dispose()
$tileCyan.Dispose(); $tileWhite.Dispose(); $hintBrush.Dispose()
$hintFont.Dispose(); $titleFormat.Dispose()
$splashGraphics.Dispose()
$splash.Save((Join-Path $launcherDir 'splash-black.png'), [System.Drawing.Imaging.ImageFormat]::Png)
$splash.Dispose()

Write-Output 'Generated app icons and the launcher branded 1920x1080 splash screen.'
