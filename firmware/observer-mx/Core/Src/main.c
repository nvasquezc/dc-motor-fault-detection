/* USER CODE BEGIN Header */
/**
  ******************************************************************************
  * @file           : main.c
  * @brief          : Observador de perturbacion + control PI + telemetria
  *                   Jitter Ingenieria SAS
  ******************************************************************************
  */
/* USER CODE END Header */
/* Includes ------------------------------------------------------------------*/
#include "main.h"
#include "adc.h"
#include "dma.h"
#include "i2s.h"
#include "tim.h"
#include "usart.h"
#include "gpio.h"

/* Private includes ----------------------------------------------------------*/
/* USER CODE BEGIN Includes */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
/* USER CODE END Includes */

/* Private typedef -----------------------------------------------------------*/
/* USER CODE BEGIN PTD */

/* USER CODE END PTD */

/* Private define ------------------------------------------------------------*/
/* USER CODE BEGIN PD */

/* USER CODE END PD */

/* Private macro -------------------------------------------------------------*/
/* USER CODE BEGIN PM */

/* USER CODE END PM */

/* Private variables ---------------------------------------------------------*/

/* USER CODE BEGIN PV */

/*=========================================================
=   PARAMETROS DEL SISTEMA
=========================================================*/
#define TS_NOMINAL     0.01f      /* 10 ms */
#define PWM_ARR        5249.0f    /* ARR de TIM3 -> 16 kHz */
#define PPR_REAL       1266.0f    /* cuentas TIM2 por vuelta (x4) */
#define STALL_US       50000U     /* margen holgado vs wrap TIM4 (65.5 ms) */
#define DT_US_MIN      200U       /* cota inferior plausible entre flancos */
#define DT_US_MAX      60000U     /* cota superior plausible entre flancos */
#define W_MAX_FISICO   500.0f     /* RPM: cota de plausibilidad */
#define ADC_BUF_LEN    64         /* 32 scans x 2 canales */
#define R_IS_OHM       4700.0f
#define K_ILIS         8500.0f
#define VREF           3.3f

/*=========================================================
=   MODELO IDENTIFICADO
=   w[k+1] = (1-a) w[k] + b (u[k] - d[k])
=   u, d en % de duty ; w en RPM
=========================================================*/
float mod_a = 0.0500f;    /* PLACEHOLDER - identificar (Parte 4) */
float mod_b = 0.1000f;    /* PLACEHOLDER - identificar (Parte 4) */

/*=========================================================
=   FILTRO DE KALMAN  x = [w_hat, d_hat]
=========================================================*/
float x1 = 0.0f, x2 = 0.0f;            /* w_hat [RPM], d_hat [%duty] */
float P11 = 100.0f, P12 = 0.0f;
float P21 = 0.0f,   P22 = 100.0f;

float kf_q1 = 0.50f;      /* ruido de proceso en w */
float kf_q2 = 0.02f;      /* ruido de proceso en d (lento = degradacion) */
float kf_R  = 0.50f;      /* varianza de la medida M/T [RPM^2] */

/*=========================================================
=   MEDICION M/T  (compartidas con la ISR de TIM4)
=========================================================*/
volatile uint16_t cap_t_us      = 0;
volatile uint32_t cap_cnt       = 0;
volatile uint8_t  cap_nueva     = 0;
volatile uint8_t  cap_n_flancos = 0;

uint16_t cap_t_us_prev   = 0;
uint32_t cap_cnt_prev    = 0;
uint8_t  mt_inicializado = 0;
uint8_t  n_flancos       = 0;   /* flancos por ventana de control */

float    w_raw = 0.0f;          /* velocidad M/T [RPM] */
uint8_t  medida_valida = 0;
uint32_t t_ultimo_flanco_us = 0;

/*=========================================================
=   BASE DE TIEMPO
=========================================================*/
volatile uint8_t  tick_control = 0;
uint32_t muestra_k = 0;
uint32_t t_us      = 0;
uint32_t t_us_prev = 0;
float    dt_real   = TS_NOMINAL;

/*=========================================================
=   REFERENCIA
=========================================================*/
float referencia_objetivo = 0.0f;
float referencia          = 0.0f;
const float RAMPA_RPM_SEG = 20.0f;

/*=========================================================
=   CONTROLADOR PI  (en % de duty)
=========================================================*/
float Kp = 0.35f;         /* re-sintonizar tras identificar */
float Ki = 1.20f;
float error    = 0.0f;
float integral = 0.0f;
float u_pi     = 0.0f;
float duty     = 0.0f;

const float DUTY_MIN = 0.0f;
const float DUTY_MAX = 95.0f;

/*=========================================================
=   MODO MANUAL (identificacion y ensayos)
=   Arranca en manual con duty 0: seguro por defecto.
=========================================================*/
uint8_t modo_manual = 1;
float   duty_manual = 0.0f;

/*=========================================================
=   ADC / CORRIENTE
=========================================================*/
uint16_t adc_buf[ADC_BUF_LEN];
float i_r = 0.0f, i_l = 0.0f;

/*=========================================================
=   PROTECCIONES Y BANDERAS
=========================================================*/
uint8_t flags = 0;
#define F_STALL     0x01
#define F_SAT       0x02
#define F_NO_EDGE   0x04
#define F_FALLO_PWM 0x08
#define F_GLITCH    0x10
#define F_MANUAL    0x20

uint32_t contador_sat = 0;
const uint32_t TIEMPO_SAT_MAX = 300;

/*=========================================================
=   TELEMETRIA
=========================================================*/
char uart_tx[192];
volatile uint8_t uart_ocupado = 0;

/*=========================================================
=   RECEPCION DE COMANDOS
=   R<rpm>  referencia objetivo      D<%>  duty manual
=   A       modo automatico          P<x>  Kp
=   I<x>    Ki                       Z     reset estados
=========================================================*/
uint8_t rx_byte = 0;
char    rx_buf[32];
uint8_t rx_idx = 0;

/* USER CODE END PV */

/* Private function prototypes -----------------------------------------------*/
void SystemClock_Config(void);
/* USER CODE BEGIN PFP */
void Medicion_MT(void);
void Kalman_Update(uint8_t hay_medida);
void Referencia_Update(void);
void PI_Update(void);
void Motor_SetDuty(float d);
void ADC_Procesar(void);
void Protecciones_Update(void);
void Telemetria_Enviar(void);
void Estados_Reset(void);
uint8_t crc8(const char *s, int n);
/* USER CODE END PFP */

/* Private user code ---------------------------------------------------------*/
/* USER CODE BEGIN 0 */

/* USER CODE END 0 */

/**
  * @brief  The application entry point.
  * @retval int
  */
int main(void)
{

  /* USER CODE BEGIN 1 */

  /* USER CODE END 1 */

  /* MCU Configuration--------------------------------------------------------*/

  /* Reset of all peripherals, Initializes the Flash interface and the Systick. */
  HAL_Init();

  /* USER CODE BEGIN Init */

  /* USER CODE END Init */

  /* Configure the system clock */
  SystemClock_Config();

  /* USER CODE BEGIN SysInit */

  /* USER CODE END SysInit */

  /* Initialize all configured peripherals */
  MX_GPIO_Init();
  MX_DMA_Init();
  MX_I2S3_Init();
  MX_TIM2_Init();
  MX_TIM3_Init();
  MX_USART2_UART_Init();
  MX_ADC1_Init();
  MX_TIM4_Init();
  MX_TIM5_Init();
  MX_TIM6_Init();
  /* USER CODE BEGIN 2 */

  /* Encoder en cuadratura */
  HAL_TIM_Encoder_Start(&htim2, TIM_CHANNEL_ALL);

  /* Base de tiempo global en microsegundos */
  HAL_TIM_Base_Start(&htim5);

  /* Captura de flancos de QA */
  HAL_TIM_IC_Start_IT(&htim4, TIM_CHANNEL_1);

  /* PWM: arranque en cero */
  HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_1);
  HAL_TIM_PWM_Start(&htim3, TIM_CHANNEL_2);
  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, 0);
  __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);

  /* ADC continuo por DMA */
  HAL_ADC_Start_DMA(&hadc1, (uint32_t*)adc_buf, ADC_BUF_LEN);

  /* Recepcion de comandos byte a byte */
  HAL_UART_Receive_IT(&huart2, &rx_byte, 1);

  /* Arranque del lazo de control a 100 Hz */
  t_us_prev = TIM5->CNT;
  t_ultimo_flanco_us = TIM5->CNT;
  HAL_TIM_Base_Start_IT(&htim6);

  /* USER CODE END 2 */

  /* Infinite loop */
  /* USER CODE BEGIN WHILE */
  while (1)
  {
    /* USER CODE END WHILE */

    /* USER CODE BEGIN 3 */
      if (tick_control)
      {
          tick_control = 0;

          HAL_GPIO_WritePin(GPIOD, LD4_Pin, GPIO_PIN_SET);   /* sonda scope */

          t_us    = TIM5->CNT;
          dt_real = (float)((uint32_t)(t_us - t_us_prev)) * 1e-6f;
          t_us_prev = t_us;

          Medicion_MT();
          Kalman_Update(medida_valida);
          Referencia_Update();

          if (modo_manual)
          {
              duty = duty_manual;
              if (duty > DUTY_MAX) duty = DUTY_MAX;
              if (duty < DUTY_MIN) duty = DUTY_MIN;
              u_pi = duty;
              error = referencia - x1;
              flags |= F_MANUAL;
          }
          else
          {
              PI_Update();
          }

          ADC_Procesar();
          Protecciones_Update();
          Motor_SetDuty(duty);
          Telemetria_Enviar();

          muestra_k++;

          HAL_GPIO_WritePin(GPIOD, LD4_Pin, GPIO_PIN_RESET);
      }
  }
  /* USER CODE END 3 */
}

/**
  * @brief System Clock Configuration
  * @retval None
  */
void SystemClock_Config(void)
{
  RCC_OscInitTypeDef RCC_OscInitStruct = {0};
  RCC_ClkInitTypeDef RCC_ClkInitStruct = {0};

  /** Configure the main internal regulator output voltage
  */
  __HAL_RCC_PWR_CLK_ENABLE();
  __HAL_PWR_VOLTAGESCALING_CONFIG(PWR_REGULATOR_VOLTAGE_SCALE1);

  /** Initializes the RCC Oscillators according to the specified parameters
  * in the RCC_OscInitTypeDef structure.
  */
  RCC_OscInitStruct.OscillatorType = RCC_OSCILLATORTYPE_HSE;
  RCC_OscInitStruct.HSEState = RCC_HSE_ON;
  RCC_OscInitStruct.PLL.PLLState = RCC_PLL_ON;
  RCC_OscInitStruct.PLL.PLLSource = RCC_PLLSOURCE_HSE;
  RCC_OscInitStruct.PLL.PLLM = 8;
  RCC_OscInitStruct.PLL.PLLN = 336;
  RCC_OscInitStruct.PLL.PLLP = RCC_PLLP_DIV2;
  RCC_OscInitStruct.PLL.PLLQ = 7;
  if (HAL_RCC_OscConfig(&RCC_OscInitStruct) != HAL_OK)
  {
    Error_Handler();
  }

  /** Initializes the CPU, AHB and APB buses clocks
  */
  RCC_ClkInitStruct.ClockType = RCC_CLOCKTYPE_HCLK|RCC_CLOCKTYPE_SYSCLK
                              |RCC_CLOCKTYPE_PCLK1|RCC_CLOCKTYPE_PCLK2;
  RCC_ClkInitStruct.SYSCLKSource = RCC_SYSCLKSOURCE_PLLCLK;
  RCC_ClkInitStruct.AHBCLKDivider = RCC_SYSCLK_DIV1;
  RCC_ClkInitStruct.APB1CLKDivider = RCC_HCLK_DIV4;
  RCC_ClkInitStruct.APB2CLKDivider = RCC_HCLK_DIV2;

  if (HAL_RCC_ClockConfig(&RCC_ClkInitStruct, FLASH_LATENCY_5) != HAL_OK)
  {
    Error_Handler();
  }
}

/* USER CODE BEGIN 4 */

/*=========================================================
=   ISR: base de tiempo del lazo (100 Hz)
=========================================================*/
void HAL_TIM_PeriodElapsedCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM6)
        tick_control = 1;
}

/*=========================================================
=   ISR: captura de flanco de QA
=   Marca de tiempo por hardware: sin jitter de latencia.
=   Conserva el ULTIMO flanco de la ventana y cuenta cuantos
=   hubo. Ambos extremos del intervalo caen sobre flancos
=   reales, por lo que dcnt y dt_us son exactos.
=========================================================*/
void HAL_TIM_IC_CaptureCallback(TIM_HandleTypeDef *htim)
{
    if (htim->Instance == TIM4 && htim->Channel == HAL_TIM_ACTIVE_CHANNEL_1)
    {
        if (cap_n_flancos < 255) cap_n_flancos++;

        cap_t_us  = (uint16_t)TIM4->CCR1;
        cap_cnt   = TIM2->CNT;
        cap_nueva = 1;
    }
}

/*=========================================================
=   MEDICION M/T
=   Velocidad entre instantes de flanco, no entre ticks.
=   Elimina la cuantizacion del lado temporal.
=========================================================*/
void Medicion_MT(void)
{
    uint16_t t_loc;
    uint32_t c_loc;
    uint8_t  nueva;

    __disable_irq();
    nueva         = cap_nueva;
    t_loc         = cap_t_us;
    c_loc         = cap_cnt;
    n_flancos     = cap_n_flancos;
    cap_nueva     = 0;
    cap_n_flancos = 0;
    __enable_irq();

    medida_valida = 0;

    if (nueva)
    {
        t_ultimo_flanco_us = t_us;
        flags &= ~(F_STALL | F_NO_EDGE);

        if (!mt_inicializado)
        {
            cap_t_us_prev   = t_loc;
            cap_cnt_prev    = c_loc;
            mt_inicializado = 1;
            return;
        }

        uint16_t dt_us = (uint16_t)(t_loc - cap_t_us_prev);
        int32_t  dcnt  = (int32_t)(c_loc - cap_cnt_prev);

        if (dt_us > DT_US_MIN && dt_us < DT_US_MAX)
        {
            float w = ((float)dcnt * 60.0f) /
                      (PPR_REAL * ((float)dt_us * 1e-6f));

            if (w > -W_MAX_FISICO && w < W_MAX_FISICO)
            {
                w_raw = w;
                medida_valida = 1;
            }
            else
            {
                flags |= F_GLITCH;
            }
        }
        else
        {
            flags |= F_GLITCH;
        }

        cap_t_us_prev = t_loc;
        cap_cnt_prev  = c_loc;
    }
    else
    {
        flags |= F_NO_EDGE;

        if ((uint32_t)(t_us - t_ultimo_flanco_us) > STALL_US)
        {
            w_raw = 0.0f;
            medida_valida   = 1;   /* la ausencia de flancos ES informacion */
            mt_inicializado = 0;   /* re-sincroniza al reanudar el giro */
            flags |= F_STALL;
        }
    }
}

/*=========================================================
=   FILTRO DE KALMAN  x = [w_hat, d_hat]
=   F = [[1-a, -b],[0, 1]]   G = [b, 0]'   H = [1, 0]
=   d_hat: perturbacion referida a la entrada, en % de duty.
=   Sin medida disponible solo predice: manejo nativo de
=   muestras faltantes a baja velocidad.
=========================================================*/
void Kalman_Update(uint8_t hay_medida)
{
    const float a = mod_a;
    const float b = mod_b;
    const float f11 = 1.0f - a;

    /* ---- Prediccion del estado ---- */
    float x1p = f11 * x1 - b * x2 + b * duty;
    float x2p = x2;

    /* ---- Prediccion de covarianza: P = F P F' + Q ---- */
    float m11 = f11 * P11 - b * P21;
    float m12 = f11 * P12 - b * P22;
    float m21 = P21;
    float m22 = P22;

    float Pp11 = m11 * f11 - m12 * b + kf_q1;
    float Pp12 = m12;
    float Pp21 = m21 * f11 - m22 * b;
    float Pp22 = m22 + kf_q2;

    if (hay_medida)
    {
        float S   = Pp11 + kf_R;
        float K1  = Pp11 / S;
        float K2  = Pp21 / S;
        float inn = w_raw - x1p;

        x1 = x1p + K1 * inn;
        x2 = x2p + K2 * inn;

        P11 = Pp11 - K1 * Pp11;
        P12 = Pp12 - K1 * Pp12;
        P21 = Pp21 - K2 * Pp11;
        P22 = Pp22 - K2 * Pp12;
    }
    else
    {
        x1  = x1p;  x2  = x2p;
        P11 = Pp11; P12 = Pp12;
        P21 = Pp21; P22 = Pp22;
    }
}

/*=========================================================
=   GENERADOR DE REFERENCIA (rampa suave)
=========================================================*/
void Referencia_Update(void)
{
    float inc = RAMPA_RPM_SEG * dt_real;

    if (referencia < referencia_objetivo)
    {
        referencia += inc;
        if (referencia > referencia_objetivo) referencia = referencia_objetivo;
    }
    else if (referencia > referencia_objetivo)
    {
        referencia -= inc;
        if (referencia < referencia_objetivo) referencia = referencia_objetivo;
    }
}

/*=========================================================
=   CONTROLADOR PI EN % DE DUTY
=   Anti-windup por integracion condicional.
=========================================================*/
void PI_Update(void)
{
    error = referencia - x1;

    float integral_temp = integral + error * dt_real;
    float u_temp = Kp * error + Ki * integral_temp;

    if (u_temp >= DUTY_MIN && u_temp <= DUTY_MAX)
        integral = integral_temp;
    else
        flags |= F_SAT;

    u_pi = Kp * error + Ki * integral;

    duty = u_pi;
    if (duty > DUTY_MAX) duty = DUTY_MAX;
    if (duty < DUTY_MIN) duty = DUTY_MIN;
}

/*=========================================================
=   ACTUADOR
=   duty en 0..100 % -> CCR directo, sin inversion.
=   Si el motor gira al reves, INTERCAMBIA M+ y M-.
=   No lo corrijas en software.
=========================================================*/
void Motor_SetDuty(float d)
{
    if (d > DUTY_MAX) d = DUTY_MAX;
    if (d < DUTY_MIN) d = DUTY_MIN;

    uint32_t ccr = (uint32_t)((d * 0.01f) * PWM_ARR);

    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_1, ccr);
    __HAL_TIM_SET_COMPARE(&htim3, TIM_CHANNEL_2, 0);
}

/*=========================================================
=   CORRIENTE (BTS7960 IS)
=   CALIBRAR contra multimetro antes de reportar amperios.
=========================================================*/
void ADC_Procesar(void)
{
    uint32_t s_r = 0, s_l = 0;

    for (int i = 0; i < ADC_BUF_LEN; i += 2)
    {
        s_r += adc_buf[i];
        s_l += adc_buf[i+1];
    }

    float n = (float)(ADC_BUF_LEN / 2);
    float v_r = ((float)s_r / n) * VREF / 4095.0f;
    float v_l = ((float)s_l / n) * VREF / 4095.0f;

    i_r = (v_r / R_IS_OHM) * K_ILIS;
    i_l = (v_l / R_IS_OHM) * K_ILIS;
}

/*=========================================================
=   PROTECCIONES
=========================================================*/
void Protecciones_Update(void)
{
    if (duty >= DUTY_MAX - 0.5f)
    {
        contador_sat++;
        if (contador_sat >= TIEMPO_SAT_MAX) flags |= F_FALLO_PWM;
    }
    else
    {
        contador_sat = 0;
    }

    if (flags & F_FALLO_PWM)
    {
        duty     = 0.0f;
        integral = 0.0f;
    }
}

/*=========================================================
=   RESET DE ESTADOS (comando Z / recuperacion de fallo)
=========================================================*/
void Estados_Reset(void)
{
    integral = 0.0f;
    x1 = 0.0f;  x2 = 0.0f;
    P11 = 100.0f; P12 = 0.0f;
    P21 = 0.0f;   P22 = 100.0f;
    mt_inicializado = 0;
    contador_sat = 0;
    flags = 0;
    referencia = 0.0f;
}

/*=========================================================
=   CRC-8  (polinomio 0x07)
=========================================================*/
uint8_t crc8(const char *s, int n)
{
    uint8_t c = 0;
    for (int i = 0; i < n; i++)
    {
        c ^= (uint8_t)s[i];
        for (int j = 0; j < 8; j++)
            c = (c & 0x80) ? (uint8_t)((c << 1) ^ 0x07) : (uint8_t)(c << 1);
    }
    return c;
}

/*=========================================================
=   TELEMETRIA POR DMA
=   k,t_us,ref,w_raw,w_hat,d_hat,e,I,u,duty,i_r,i_l,nf,flags*CRC
=========================================================*/
void Telemetria_Enviar(void)
{
    if (uart_ocupado) return;

    int n = sprintf(uart_tx,
        "%lu,%lu,%.3f,%.3f,%.3f,%.4f,%.3f,%.4f,%.3f,%.3f,%.4f,%.4f,%u,%u",
        (unsigned long)muestra_k,
        (unsigned long)t_us,
        referencia, w_raw, x1, x2,
        error, integral, u_pi, duty,
        i_r, i_l,
        (unsigned)n_flancos,
        (unsigned)flags);

    uint8_t c = crc8(uart_tx, n);
    n += sprintf(uart_tx + n, "*%02X\r\n", c);

    uart_ocupado = 1;
    if (HAL_UART_Transmit_DMA(&huart2, (uint8_t*)uart_tx, n) != HAL_OK)
        uart_ocupado = 0;

    /* Las banderas transitorias se limpian por muestra.
       F_FALLO_PWM y F_MANUAL son persistentes. */
    flags &= (F_FALLO_PWM | F_MANUAL);
    if (!modo_manual) flags &= ~F_MANUAL;
}

void HAL_UART_TxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance == USART2) uart_ocupado = 0;
}

/*=========================================================
=   RECEPCION DE COMANDOS
=   R<rpm>  referencia objetivo    D<%>  duty manual
=   A       modo automatico        P<x>  Kp
=   I<x>    Ki                     Z     reset de estados
=========================================================*/
void HAL_UART_RxCpltCallback(UART_HandleTypeDef *huart)
{
    if (huart->Instance != USART2) return;

    if (rx_byte == '\n' || rx_byte == '\r')
    {
        rx_buf[rx_idx] = '\0';

        if (rx_idx >= 1)
        {
            float v = (rx_idx > 1) ? (float)atof(rx_buf + 1) : 0.0f;

            switch (rx_buf[0])
            {
                case 'R':
                    referencia_objetivo = v;
                    break;

                case 'D':
                    duty_manual = v;
                    modo_manual = 1;
                    break;

                case 'A':
                    modo_manual = 0;
                    integral = 0.0f;
                    break;

                case 'P':
                    Kp = v;
                    break;

                case 'I':
                    Ki = v;
                    break;

                case 'Z':
                    Estados_Reset();
                    break;

                default:
                    break;
            }
        }
        rx_idx = 0;
    }
    else if (rx_idx < (sizeof(rx_buf) - 1))
    {
        rx_buf[rx_idx++] = (char)rx_byte;
    }
    else
    {
        rx_idx = 0;   /* trama sobredimensionada: descartar */
    }

    HAL_UART_Receive_IT(&huart2, &rx_byte, 1);
}

/* USER CODE END 4 */

/**
  * @brief  This function is executed in case of error occurrence.
  * @retval None
  */
void Error_Handler(void)
{
  /* USER CODE BEGIN Error_Handler_Debug */
  __disable_irq();
  while (1)
  {
  }
  /* USER CODE END Error_Handler_Debug */
}

#ifdef  USE_FULL_ASSERT
/**
  * @brief  Reports the name of the source file and the source line number
  *         where the assert_param error has occurred.
  * @param  file: pointer to the source file name
  * @param  line: assert_param error line source number
  * @retval None
  */
void assert_failed(uint8_t *file, uint32_t line)
{
  /* USER CODE BEGIN 6 */
  /* USER CODE END 6 */
}
#endif /* USE_FULL_ASSERT */
